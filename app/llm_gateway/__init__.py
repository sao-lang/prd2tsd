"""LLM Gateway — 统一模型调用门面。

Block F 增强链路：
1. 前置护栏（Prompt 注入检测 / PII 检测）
2. 速率限制检查
3. 模型路由
4. 预算检查（自动降级）
5. 语义缓存
6. Circuit Breaker + Failover 链
7. 追踪 + LLM 调用
8. 后置护栏（内容安全 / 输出校验）
9. 设置缓存 / 成本 / 预算 / 速率记录
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from typing import Any

from opentelemetry import trace

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerManager
from app.core.config import settings
from app.core.logger import get_logger
from app.llm_gateway.budget_controller import BudgetController, budget_controller
from app.llm_gateway.cache import SemanticCache
from app.llm_gateway.capabilities.embedding import UnifiedEmbedding
from app.llm_gateway.capabilities.reranking import UnifiedReranking
from app.llm_gateway.config_manager import ModelConfigManager
from app.llm_gateway.cost_tracker import CostRecord, CostTracker
from app.llm_gateway.failover import FailoverManager, FailoverTarget
from app.llm_gateway.guardrails import GuardrailManager
from app.llm_gateway.guardrails.base import GuardrailResult
from app.llm_gateway.guardrails.content_safety import ContentSafetyGuardrail
from app.llm_gateway.guardrails.output_validator import OutputValidatorGuardrail
from app.llm_gateway.guardrails.pii_detector import PIIDetectorGuardrail
from app.llm_gateway.guardrails.prompt_injection import PromptInjectionGuardrail
from app.llm_gateway.models import (
    ChatMessage,
    CompletionUsage,
    EmbeddingResponse,
    LLMResponse,
    RerankResponse,
)
from app.llm_gateway.providers import ProviderFactory
from app.llm_gateway.rate_limiter import RateLimiter, rate_limiter
from app.observability.metrics import LLM_CALL_TOTAL, LLM_COST_TOTAL, track_llm_call
from app.observability.tracing import tracer
from app.security.data_masking import DataMaskingEngine
from contracts.models import ModelType, RoutingRule

logger = get_logger("prd2tsd.gateway")

# 全局单例
config_manager = ModelConfigManager()

# 数据脱敏引擎单例（LLM 调用链输入脱敏 / 输出还原）
_masking_engine = DataMaskingEngine()
_request_model_overrides: ContextVar[dict[str, Any] | None] = ContextVar(
    "gateway_request_model_overrides",
    default=None,
)


@contextmanager
def gateway_request_context(**overrides: Any) -> Any:
    """为当前异步上下文设置请求级模型覆盖，子 Task 会安全继承。"""
    clean = {key: value for key, value in overrides.items() if value not in (None, "")}
    token = _request_model_overrides.set(clean)
    try:
        yield
    finally:
        _request_model_overrides.reset(token)


class LLMGateway:
    """LLM Gateway 门面类 — 统一对外接口。

    Block F 增强：
    - Circuit Breaker：每个 Provider 独立熔断
    - Failover 链：Primary → Fallback → Ultimate
    - Guardrails：前置（注入/PII）+ 后置（安全/输出校验）
    """

    def __init__(
        self,
        config_manager: ModelConfigManager | None = None,
        provider_factory: ProviderFactory | None = None,
        cost_tracker: CostTracker | None = None,
        cache: SemanticCache | None = None,
        budget_controller: BudgetController | None = None,
        rate_limiter: RateLimiter | None = None,
        embedding: UnifiedEmbedding | None = None,
        reranking: UnifiedReranking | None = None,
    ) -> None:
        """初始化 LLM Gateway。

        Args:
            config_manager: 模型配置管理器。
            provider_factory: Provider 工厂。
            cost_tracker: 成本追踪器。
            cache: 语义缓存。
            budget_controller: 预算控制器。
            rate_limiter: 速率限制器。
            embedding: UnifiedEmbedding 实例。
            reranking: UnifiedReranking 实例。
        """
        self.config_manager = config_manager or ModelConfigManager()
        self.provider_factory = provider_factory or ProviderFactory()
        self.cost_tracker = cost_tracker or CostTracker()
        self.cache = cache or SemanticCache()
        self.budget_controller = budget_controller or BudgetController()
        self.rate_limiter = rate_limiter or RateLimiter()

        # ── Block F: Failover 管理器 ──
        self.failover = FailoverManager()
        self._init_failover_chains()

        # ── Block F: 护栏管理器 ──
        self.guardrails = GuardrailManager()
        self._init_guardrails()

        # ── Block F: Provider Circuit Breakers ──
        self._init_circuit_breakers()

        # Capabilities（API 优先，本地模型兜底）
        self.embedding_cap = embedding or UnifiedEmbedding(
            config_manager=self.config_manager,
            provider_factory=self.provider_factory,
        )
        self.reranking_cap = reranking or UnifiedReranking(
            config_manager=self.config_manager,
            provider_factory=self.provider_factory,
        )

    def _init_failover_chains(self) -> None:
        """从用途级配置初始化可观测的 Failover 链。"""
        for task_type in ("analysis", "planning", "generation", "evaluation", "vision"):
            rule = self.config_manager.resolve_rule(task_type)
            self._configure_route_failover(task_type, rule)
        logger.info("Failover 链初始化完成")

    def _init_guardrails(self) -> None:
        """注册默认护栏。"""
        from app.llm_gateway.guardrails.empty_response_guardrail import EmptyResponseGuardrail
        from app.llm_gateway.guardrails.retry_decision_guardrail import RetryDecisionGuardrail
        from app.llm_gateway.guardrails.timeout_guardrail import TimeoutGuardrail

        self.guardrails.register(PromptInjectionGuardrail(settings.PROMPT_INJECTION_BLOCK_THRESHOLD))
        self.guardrails.register(PIIDetectorGuardrail())
        self.guardrails.register(TimeoutGuardrail())
        self.guardrails.register(ContentSafetyGuardrail())
        self.guardrails.register(OutputValidatorGuardrail())
        self.guardrails.register(EmptyResponseGuardrail())
        self.guardrails.register(RetryDecisionGuardrail())
        logger.info("护栏初始化完成: 7 个护栏已注册")

    def _init_circuit_breakers(self) -> None:
        """初始化 Provider Circuit Breakers。"""
        for provider_name in ["deepseek", "openai", "anthropic", "cohere"]:
            cb = CircuitBreaker(
                name=f"provider:{provider_name}",
                failure_threshold=3,
                recovery_timeout=30.0,
            )
            CircuitBreakerManager.register(cb)
        logger.info("Circuit Breaker 初始化完成")

    @staticmethod
    def _breaker_name(provider: str) -> str:
        """返回兼容既有监控指标的 Provider 熔断器名称。"""
        return f"provider:{provider}"

    def _ensure_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """为任意动态 Provider 获取或创建熔断器。"""
        name = self._breaker_name(provider)
        breaker = CircuitBreakerManager.get(name)
        if breaker is None:
            breaker = CircuitBreaker(name=name, failure_threshold=3, recovery_timeout=30.0)
            CircuitBreakerManager.register(breaker)
        return breaker

    def _resolve_route(self, task_type: str, kwargs: dict[str, Any]) -> tuple[RoutingRule, float]:
        """解析请求覆盖后的路由和单次调用超时，并移除 Gateway 专用参数。"""
        inherited = _request_model_overrides.get() or {}
        requested_provider = str(kwargs.pop("provider", inherited.get("provider", "")) or "")
        requested_model = str(kwargs.pop("model", inherited.get("model", "")) or "")
        requested_timeout = kwargs.pop("timeout", inherited.get("timeout"))
        if "estimated_tokens" not in kwargs and inherited.get("estimated_tokens") is not None:
            kwargs["estimated_tokens"] = inherited["estimated_tokens"]
        if "max_tokens" not in kwargs and inherited.get("max_tokens") is not None:
            kwargs["max_tokens"] = inherited["max_tokens"]
        rule = self.config_manager.resolve_rule(task_type, requested_provider, requested_model)
        model_config = self.config_manager.get_config(rule.type, rule.provider)
        timeout = float(requested_timeout or rule.timeout or model_config.timeout)
        return rule, max(0.001, timeout)

    @staticmethod
    def _estimate_tokens(prompt: str, kwargs: dict[str, Any]) -> int:
        """估算输入与最大输出 Token，用于调用前 TPM 预留。"""
        explicit = kwargs.pop("estimated_tokens", None)
        if explicit is not None:
            return max(0, int(explicit))
        input_tokens = max(1, len(prompt) // 4)
        output_tokens = max(0, int(kwargs.get("max_tokens", 4096)))
        return input_tokens + output_tokens

    @staticmethod
    def _route_key(task_type: str, rule: RoutingRule) -> str:
        """构造隔离到任务路由的 Failover 状态键。"""
        return f"{task_type}:{rule.type.value}:{rule.provider}:{rule.model}"

    def _configure_route_failover(self, task_type: str, rule: RoutingRule) -> tuple[str, list[FailoverTarget]]:
        """用已解析主目标及配置回退目标生成本次执行链。"""
        targets = [
            FailoverTarget(
                provider=rule.provider,
                model=rule.model,
                priority=0,
                model_type=rule.type.value,
            )
        ]
        for priority, fallback in enumerate(rule.fallbacks, start=1):
            provider = str(fallback.get("provider", ""))
            model = str(fallback.get("model", ""))
            if provider and model and (provider, model) != (rule.provider, rule.model):
                targets.append(
                    FailoverTarget(
                        provider=provider,
                        model=model,
                        priority=priority,
                        model_type=str(fallback.get("type", rule.type.value)),
                    )
                )
        route_key = self._route_key(task_type, rule)
        self.failover.configure(route_key, targets)
        return route_key, targets

    def _route_breakers(self, rule: RoutingRule) -> list[CircuitBreaker]:
        """返回主路由和回退路由涉及的全部熔断器。"""
        providers = [rule.provider, *(str(item.get("provider", "")) for item in rule.fallbacks)]
        return [self._ensure_circuit_breaker(provider) for provider in dict.fromkeys(providers) if provider]

    async def _cache_embedding(self, text: str) -> tuple[list[float], str]:
        """为语义缓存生成稳定向量；失败时返回空向量并跳过语义层。"""
        try:
            response = await self.embedding_cap.embed(
                texts=[text],
                task_type="embedding",
                mode="local",
            )
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("语义缓存向量生成失败: %s", exc)
            return [], ""
        embedding = response.embeddings[0] if response.embeddings else []
        return embedding, response.model or "local-semantic-cache"

    async def _guard_input(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> tuple[str, GuardrailResult | None]:
        """执行统一的 LLM 输入护栏与可逆脱敏。

        Args:
            prompt: 原始提示词。
            context: 护栏上下文。

        Returns:
            (可发送给 Provider 的提示词, 拦截结果)。未拦截时第二项为 None。
        """
        input_results = await self.guardrails.check_input(prompt, context)
        guarded_prompt = prompt
        for result in input_results:
            if result.blocked:
                return prompt, result
            if result.masked_text is not None:
                guarded_prompt = result.masked_text

        # 先应用护栏的强制脱敏结果，再补充数据分级引擎覆盖的 L3 敏感数据。
        # 使第三方 LLM 不会接收护栏已识别的 PII/API Key/Token 原文。
        if guarded_prompt:
            guarded_prompt = _masking_engine.mask_reversible(guarded_prompt, level="L3")
        return guarded_prompt, None

    async def _guard_output(
        self,
        content: str,
        context: dict[str, Any],
    ) -> tuple[str, GuardrailResult | None]:
        """执行统一的 LLM 输出护栏与脱敏 token 还原。

        Args:
            content: Provider 返回的完整内容。
            context: 护栏上下文。

        Returns:
            (可交付给调用方的内容, 触发的拦截结果)。
        """
        # 可逆脱敏 token 可能被模型原样返回，必须先还原再执行输出护栏，
        # 否则还原出的敏感值会绕过内容安全检查。
        unmasked_content = _masking_engine.unmask(content)
        output_results = await self.guardrails.check_output(unmasked_content, context)
        blocked_result: GuardrailResult | None = None
        guarded_content = unmasked_content
        for result in output_results:
            if not result.blocked:
                continue
            blocked_result = result
            if result.masked_text is not None:
                guarded_content = result.masked_text
            else:
                guarded_content = f"[输出被护栏拦截: {result.reason}]"
                break

        return guarded_content, blocked_result

    async def complete(
        self,
        prompt: str,
        task_type: str = "default",
        workspace_id: str = "",
        layer: str = "",
        node: str = "",
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 LLM 生成文本。

        Block F 增强链路：
        0. 前置护栏（Prompt 注入 / PII 检测）
        1. 速率限制检查
        2. 模型路由
        3. 预算检查（自动降级）
        4. 语义缓存
        5. Circuit Breaker + Failover 链（自动切换 Provider）
        6. 追踪 + Prometheus 指标 + LLM 调用
        7. 后置护栏（内容安全 / 输出校验）
        8. 设置缓存 / 成本 / 预算 / 速率记录

        Args:
            prompt: 输入提示词。
            task_type: 任务类型，用于模型路由。
            workspace_id: 工作空间 ID。
            layer: 所属层名。
            node: 所属节点名。
            **kwargs: 额外参数传递给 Provider。

        Returns:
            LLMResponse 包含生成结果、成本、模型等信息。
        """
        rule, timeout_seconds = self._resolve_route(task_type, kwargs)
        model_config = self.config_manager.get_config(rule.type, rule.provider)
        model_name = rule.model or model_config.default_model
        primary_breaker = self._ensure_circuit_breaker(rule.provider)
        estimated_tokens = self._estimate_tokens(prompt, kwargs)

        with tracer.start_as_current_span(
            f"gateway.complete.{task_type}",
            attributes={
                "task_type": task_type,
                "workspace_id": workspace_id,
                "layer": layer,
                "node": node,
                "provider": rule.provider,
                "model": model_name,
            },
            kind=trace.SpanKind.CLIENT,
        ) as span:
            # ── 步骤 0: 前置护栏 ──
            guard_context = {
                "task_type": task_type,
                "workspace_id": workspace_id,
                "layer": layer,
                "circuit_breaker": primary_breaker,
                "circuit_breakers": self._route_breakers(rule),
                "timeout_seconds": timeout_seconds,
            }
            guarded_prompt, input_block = await self._guard_input(prompt, guard_context)
            if input_block is not None:
                span.set_attribute("guardrail_blocked", input_block.name)
                logger.warning("输入被护栏拦截: %s — %s", input_block.name, input_block.reason)
                # 护栏拦截路径也记录调用次数（避免指标低估）
                LLM_CALL_TOTAL.labels("", layer, node).inc()
                return LLMResponse(
                    content=f"[输入被护栏拦截: {input_block.reason}]",
                    model="",
                    cached=False,
                    cost=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    metadata={
                        "guardrail": input_block.name,
                        "blocked": True,
                        "reason": input_block.reason,
                    },
                )

            # ── 步骤 1: 速率限制检查 ──
            rate_result = await self.rate_limiter.reserve(workspace_id, estimated_tokens)
            if not rate_result["allowed"]:
                span.set_attribute("rate_limited", True)
                span.set_attribute("retry_after", rate_result["retry_after"])
                # 速率限制路径也记录调用次数（避免指标低估）
                LLM_CALL_TOTAL.labels("", layer, node).inc()
                return LLMResponse(
                    content="",
                    model="",
                    cached=False,
                    cost=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    metadata={"error": "rate_limited", "retry_after": rate_result["retry_after"]},
                )

            reservation_id = str(rate_result["reservation_id"])

            # ── 步骤 3: 预算检查 — 自动降级 ──
            budget_check = await self.budget_controller.check(workspace_id)
            if budget_check.get("should_downgrade"):
                low_cost_model = self._get_low_cost_model(model_name)
                span.set_attribute("budget_downgrade", True)
                span.set_attribute("original_model", model_name)
                span.set_attribute("downgraded_model", low_cost_model)
                _provider_map = {"gpt-4o-mini": "openai", "deepseek-chat": "deepseek"}
                downgrade_provider = _provider_map.get(low_cost_model, "openai")
                rule.provider = downgrade_provider
                rule.model = low_cost_model
                rule.type = ModelType.LLM
                model_name = low_cost_model

            # ── 指标追踪：包裹缓存命中 + 实际调用 + 成本（含失败路径） ──
            with track_llm_call(model_name, layer, node) as token_info:
                # ── 步骤 4: 语义缓存 ──
                cache_key = self.cache.make_key(prompt, task_type, workspace_id, model_name)
                cached = self.cache.get(cache_key)
                if cached is None and isinstance(self.cache, SemanticCache):
                    cached = await self.cache.lookup(
                        prompt=prompt,
                        task_type=task_type,
                        workspace_id=workspace_id,
                        model=model_name,
                        embedding_loader=self._cache_embedding,
                    )
                if cached is not None:
                    span.set_attribute("cache_hit", True)
                    await self.rate_limiter.reconcile(workspace_id, reservation_id, 0)
                    return LLMResponse(
                        content=cached,
                        model=model_name,
                        cached=True,
                        cost=0.0,
                        input_tokens=0,
                        output_tokens=0,
                    )

                # ── 步骤 5: Circuit Breaker + Failover 链 ──
                provider_name = rule.provider
                cb = CircuitBreakerManager.get(f"provider:{provider_name}")

                # 如果当前 Provider 已熔断，走 Failover
                if cb and not cb.is_available:
                    logger.warning("Provider %s 已熔断，走 Failover 链", provider_name)
                    span.set_attribute("circuit_broken", True)
                    span.set_attribute("broken_provider", provider_name)

                response, model_name = await self._failover_call(
                    prompt=guarded_prompt,
                    kwargs=kwargs,
                    task_type=task_type,
                    rule=rule,
                    timeout_seconds=timeout_seconds,
                )

                if response is None:
                    span.set_attribute("all_calls_failed", True)
                    await self.rate_limiter.reconcile(workspace_id, reservation_id, 0)
                    return LLMResponse(
                        content="[服务暂不可用，请稍后重试]",
                        model="",
                        cached=False,
                        cost=0.0,
                        input_tokens=0,
                        output_tokens=0,
                        metadata={"error": "all_calls_failed"},
                    )

                # ── 步骤 7: 后置护栏 ──
                expected_json = kwargs.get("response_format") is not None
                response.content, output_block = await self._guard_output(
                    response.content,
                    {"task_type": task_type, "model": model_name, "expected_json": expected_json},
                )
                if output_block is not None:
                    if output_block.masked_text is not None:
                        span.set_attribute("guardrail_masked", True)
                    else:
                        span.set_attribute("guardrail_blocked", output_block.name)

                # ── 步骤 8: 设置缓存 / 成本 / 预算 / 速率 ──
                if isinstance(self.cache, SemanticCache):
                    await self.cache.store(
                        prompt=prompt,
                        response=response.content,
                        task_type=task_type,
                        workspace_id=workspace_id,
                        model=model_name,
                        embedding_loader=self._cache_embedding,
                    )
                else:
                    self.cache.set(cache_key, response.content)

                cost_record = self.cost_tracker.record(
                    model=model_name,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    metadata={
                        "task_type": task_type,
                        "workspace_id": workspace_id,
                        "layer": layer,
                        "node": node,
                    },
                )
                if response.cost <= 0:
                    response.cost = cost_record.cost

                # 成本指标（按实际使用模型）
                LLM_COST_TOTAL.labels(model_name).inc(response.cost)

                await self.budget_controller.record_usage(
                    workspace_id,
                    response.cost,
                    model_name,
                    response.input_tokens,
                    response.output_tokens,
                    layer,
                    node,
                )

                await self.rate_limiter.reconcile(
                    workspace_id,
                    reservation_id,
                    response.input_tokens + response.output_tokens,
                )

                span.set_attribute("model", model_name)
                span.set_attribute("input_tokens", response.input_tokens)
                span.set_attribute("output_tokens", response.output_tokens)
                span.set_attribute("cost", response.cost)

                # 记录 token 指标
                token_info["input_tokens"] = response.input_tokens
                token_info["output_tokens"] = response.output_tokens

                return response

    async def stream_complete(
        self,
        prompt: str,
        task_type: str = "default",
        workspace_id: str = "",
        layer: str = "",
        node: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """安全流式调用 LLM。

        完整链路：前置护栏 → 速率限制 → 模型路由 → 预算检查 → 追踪
        → 语义缓存(跳过) → Failover + Provider.stream_complete()
        → 完整输出后置护栏 → 安全内容释放 → 成本记录。

        Provider 的原始 chunk 按单次 Failover 尝试隔离缓冲，只有完整内容
        通过后置护栏后才会交付，防止敏感片段和失败尝试的半截输出泄漏。

        Args:
            prompt: 输入提示词。
            task_type: 任务类型，用于模型路由。
            workspace_id: 工作空间 ID。
            layer: 所属层名。
            node: 所属节点名。
            **kwargs: 额外参数传递给 Provider。

        Yields:
            经完整输出护栏检查后的文本块。
        """
        rule, timeout_seconds = self._resolve_route(task_type, kwargs)
        model_name = rule.model
        estimated_tokens = self._estimate_tokens(prompt, kwargs)
        primary_breaker = self._ensure_circuit_breaker(rule.provider)

        # ── 步骤 0: 前置护栏 + 可逆脱敏 ──
        guard_context = {
            "task_type": task_type,
            "workspace_id": workspace_id,
            "layer": layer,
            "circuit_breaker": primary_breaker,
            "circuit_breakers": self._route_breakers(rule),
            "timeout_seconds": timeout_seconds,
        }
        guarded_prompt, input_block = await self._guard_input(prompt, guard_context)
        if input_block is not None:
            logger.warning("流式输入被护栏拦截: %s — %s", input_block.name, input_block.reason)
            LLM_CALL_TOTAL.labels("", layer, node).inc()
            yield f"[输入被护栏拦截: {input_block.reason}]"
            return

        # ── 步骤 1: 速率限制检查 ──
        rate_result = await self.rate_limiter.reserve(workspace_id, estimated_tokens)
        if not rate_result["allowed"]:
            yield f"[速率限制，请 {rate_result['retry_after']} 秒后重试]"
            return
        reservation_id = str(rate_result["reservation_id"])

        # ── 步骤 3: 预算检查 — 自动降级 ──
        budget_check = await self.budget_controller.check(workspace_id)
        if budget_check.get("should_downgrade"):
            low_cost_model = self._get_low_cost_model(model_name)
            rule.provider = {"gpt-4o-mini": "openai", "deepseek-chat": "deepseek"}.get(
                low_cost_model,
                "openai",
            )
            rule.model = low_cost_model
            rule.type = ModelType.LLM
            model_name = low_cost_model

        # ── 步骤 4: 安全流式缓存 ──
        if isinstance(self.cache, SemanticCache):
            cached = await self.cache.lookup(
                prompt=prompt,
                task_type=task_type,
                workspace_id=workspace_id,
                model=model_name,
                embedding_loader=self._cache_embedding,
            )
            if cached is not None:
                await self.rate_limiter.reconcile(workspace_id, reservation_id, 0)
                yield cached
                return

        # ── 步骤 5: Failover 链 + Provider 流式调用 ──
        input_tokens = 0
        output_tokens = 0
        route_key, targets = self._configure_route_failover(task_type, rule)

        # 指标追踪：包裹流式调用（流式结束后统计 token / 成本）
        with track_llm_call(model_name, layer, node) as token_info:
            for attempt, target in enumerate(targets):
                target_provider = target.provider
                try:
                    target_model = target.model
                    target_config = self.config_manager.get_config(target.model_type, target_provider)
                    cb = self._ensure_circuit_breaker(target_provider)
                    if not cb.is_available:
                        continue

                    provider = self.provider_factory.create(target_config.provider, target_config)
                    actual_model = target_model

                    async def _collect(
                        _provider: Any = provider,
                        _actual_model: str = actual_model,
                        _kwargs_items: tuple[tuple[str, Any], ...] = tuple(kwargs.items()),
                    ) -> list[str]:
                        chunks: list[str] = []
                        call_kwargs = dict(_kwargs_items)
                        async with asyncio.timeout(timeout_seconds):
                            async for chunk in _provider.stream_complete(
                                prompt=guarded_prompt,
                                model=_actual_model,
                                **call_kwargs,
                            ):
                                chunks.append(chunk)
                        return chunks

                    with tracer.start_as_current_span(
                        f"gateway.stream_complete.{task_type}",
                        attributes={
                            "task_type": task_type,
                            "workspace_id": workspace_id,
                            "layer": layer,
                            "node": node,
                            "model": actual_model,
                            "streaming": True,
                            "provider": target_provider,
                            "failover_attempt": attempt,
                        },
                        kind=trace.SpanKind.CLIENT,
                    ) as span:
                        attempt_chunks = await cb.call(_collect)

                        # ── 步骤 6: 完整输出后置护栏 ──
                        raw_content = "".join(attempt_chunks)
                        expected_json = kwargs.get("response_format") is not None
                        safe_content, output_block = await self._guard_output(
                            raw_content,
                            {
                                "task_type": task_type,
                                "model": actual_model,
                                "expected_json": expected_json,
                            },
                        )
                        if output_block is not None:
                            if output_block.masked_text is not None:
                                span.set_attribute("guardrail_masked", True)
                            else:
                                span.set_attribute("guardrail_blocked", output_block.name)

                        # ── 成本记录（流式结束后） ──
                        output_tokens = len(raw_content) // 4
                        input_tokens = len(guarded_prompt) // 4
                        cost_record = self.cost_tracker.record(
                            model=actual_model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            metadata={
                                "task_type": task_type,
                                "workspace_id": workspace_id,
                                "layer": layer,
                                "node": node,
                                "streaming": True,
                            },
                        )
                        estimated_cost = cost_record.cost

                        # 成本指标（流式按估算成本）
                        LLM_COST_TOTAL.labels(actual_model).inc(estimated_cost)

                        if workspace_id:
                            await self.budget_controller.record_usage(
                                workspace_id,
                                estimated_cost,
                                actual_model,
                                input_tokens,
                                output_tokens,
                                layer,
                                node,
                            )

                        await self.rate_limiter.reconcile(
                            workspace_id,
                            reservation_id,
                            input_tokens + output_tokens,
                        )

                        if isinstance(self.cache, SemanticCache):
                            await self.cache.store(
                                prompt=prompt,
                                response=safe_content,
                                task_type=task_type,
                                workspace_id=workspace_id,
                                model=actual_model,
                                embedding_loader=self._cache_embedding,
                            )

                        span.set_attribute("input_tokens", input_tokens)
                        span.set_attribute("output_tokens", output_tokens)
                        span.set_attribute("estimated_cost", estimated_cost)
                        token_info["input_tokens"] = input_tokens
                        token_info["output_tokens"] = output_tokens

                        # 计费/指标已落帐且护栏已通过后才释放内容。
                        # 内容未变时保留 Provider chunk 边界；护栏改写后只交付安全文本。
                        if safe_content == raw_content:
                            for chunk in attempt_chunks:
                                yield chunk
                        elif safe_content:
                            yield safe_content

                    # 成功，退出重试
                    return
                except Exception as exc:
                    logger.warning("流式调用失败 (attempt=%d): %s", attempt, exc)
                    with suppress(Exception):
                        await self.failover.record_failure(route_key, target_provider, target.model)
                    if attempt == len(targets) - 1:
                        logger.exception("流式调用全部重试失败: task_type=%s", task_type)
                        await self.rate_limiter.reconcile(workspace_id, reservation_id, 0)
                        yield f"[流式调用出错: {exc}]"
                        return

            # 所有熔断器均处于不可试探状态时不会进入异常分支，也必须回收预留并返回错误。
            await self.rate_limiter.reconcile(workspace_id, reservation_id, 0)
            yield "[流式调用出错: 所有 Provider 当前均不可用]"

            # 记录 token 指标
            token_info["input_tokens"] = input_tokens
            token_info["output_tokens"] = output_tokens

    async def _failover_call(
        self,
        prompt: str,
        kwargs: dict[str, Any],
        task_type: str,
        rule: RoutingRule,
        timeout_seconds: float,
    ) -> tuple[LLMResponse | None, str]:
        """执行 Circuit Breaker + Failover 链调用。

        Args:
            prompt: 输入提示词。
            kwargs: 调用参数。
            task_type: 路由任务类型。
            rule: 已应用请求覆盖的路由规则。
            timeout_seconds: 每个 Provider 尝试的超时秒数。

        Returns:
            (LLMResponse, model_name) 或 (None, "") 全部失败。
        """
        route_key, targets = self._configure_route_failover(task_type, rule)
        for attempt, target in enumerate(targets):
            target_provider = target.provider
            try:
                target_model = target.model
                target_config = self.config_manager.get_config(target.model_type, target_provider)
                target_cb = self._ensure_circuit_breaker(target_provider)
                if not target_cb.is_available:
                    continue

                # 构建调用闭包 — 通过参数默认值捕获循环变量
                _cfg_ref = target_config
                _mdl_ref = target_model
                _kw_ref = dict(kwargs)
                _pr_ref = prompt

                async def _call(
                    _c: Any = _cfg_ref,
                    _m: Any = _mdl_ref,
                    _p: Any = _pr_ref,
                    _k: Any = _kw_ref,
                ) -> LLMResponse:
                    kw = dict(_k)
                    provider = self.provider_factory.create(_c.provider, _c)
                    async with asyncio.timeout(timeout_seconds):
                        return await provider.complete(prompt=_p, model=_m, **kw)

                resp = await target_cb.call(_call)

                return resp, resp.model or target_model
            except Exception as exc:
                logger.warning("Provider 调用失败 (attempt=%d): %s", attempt, exc)
                with suppress(Exception):
                    await self.failover.record_failure(route_key, target_provider, target.model)

        return (None, "")

    async def analyze_vision(
        self,
        prompt: str,
        images: list[str | dict[str, Any]],
        workspace_id: str = "",
        **kwargs: Any,
    ) -> LLMResponse:
        """使用独立 vision 路由分析图片或多模态输入。"""
        return await self.complete(
            prompt=prompt,
            task_type="vision",
            workspace_id=workspace_id,
            layer="vision",
            images=images,
            **kwargs,
        )

    async def embed(
        self,
        texts: list[str],
        task_type: str = "embedding",
        mode: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """统一 Embedding — API 优先，本地模型兜底。

        通过 UnifiedEmbedding Capability 执行：
          1. API 模式：调用 OpenAI text-embedding-3-small（需配置 API Key）
          2. 本地模式：SentenceTransformer（如 BAAI/bge-large-zh-v1.5）
          3. auto 模式：API 失败时自动降级到本地

        Args:
            texts: 需要向量化的文本列表。
            task_type: 任务类型（用于 Gateway 路由）。
            mode: 临时覆盖模式（auto/api/local）。为 None 时使用 Capability 配置。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse 包含向量和成本信息。
        """
        workspace_id = str(kwargs.pop("workspace_id", ""))
        estimated_tokens = int(kwargs.pop("estimated_tokens", sum(max(1, len(text) // 4) for text in texts)))
        rate_result = await self.rate_limiter.reserve(workspace_id, estimated_tokens)
        if not rate_result["allowed"]:
            return EmbeddingResponse(
                embeddings=[[0.0] for _ in texts],
                model="",
                metadata={"error": "rate_limited", "retry_after": rate_result["retry_after"]},
            )

        response = await self.embedding_cap.embed(
            texts=texts,
            task_type=task_type,
            mode=mode,
            **kwargs,
        )

        await self.rate_limiter.reconcile(
            workspace_id,
            str(rate_result["reservation_id"]),
            response.input_tokens or estimated_tokens,
        )

        # 追踪成本（API 模式时）
        if response.input_tokens > 0:
            self.cost_tracker.record(
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=0,
            )
        return response

    async def rerank(
        self,
        query: str,
        docs: list[str],
        task_type: str = "rerank",
        mode: str | None = None,
        top_k: int | None = None,
        **kwargs: Any,
    ) -> RerankResponse:
        """统一 Rerank — API 优先，本地模型兜底。

        通过 UnifiedReranking Capability 执行：
          1. API 模式：Cohere Rerank API（需配置 API Key）
          2. 本地模式：BGE Cross-encoder（如 BAAI/bge-reranker-v2-m3）
          3. auto 模式：API 失败时自动降级到本地

        Args:
            query: 查询文本。
            docs: 需要重排序的文档列表。
            task_type: 任务类型。
            mode: 临时覆盖模式（auto/api/local）。
            top_k: 返回前 k 个结果。
            **kwargs: 额外参数。

        Returns:
            RerankResponse 包含排序后的文档和成本信息。
        """
        workspace_id = str(kwargs.pop("workspace_id", ""))
        default_estimate = (len(query) + sum(len(doc) for doc in docs)) // 4
        estimated_tokens = int(kwargs.pop("estimated_tokens", default_estimate))
        rate_result = await self.rate_limiter.reserve(workspace_id, estimated_tokens)
        if not rate_result["allowed"]:
            return RerankResponse(
                scores=[],
                indices=[],
                model="",
                metadata={"error": "rate_limited", "retry_after": rate_result["retry_after"]},
            )

        response = await self.reranking_cap.rerank(
            query=query,
            docs=docs,
            task_type=task_type,
            mode=mode,
            top_k=top_k,
            **kwargs,
        )

        input_tokens = response.input_tokens or (len(query) + sum(len(d) for d in docs)) // 4
        await self.rate_limiter.reconcile(workspace_id, str(rate_result["reservation_id"]), input_tokens)

        if response.input_tokens > 0:
            self.cost_tracker.record(
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=0,
            )
        return response

    @staticmethod
    def _get_low_cost_model(model: str) -> str:
        """获取低成本备用模型。

        Args:
            model: 当前模型名。

        Returns:
            低成本模型名。
        """
        downgrade_map = {
            "gpt-4o": "deepseek-chat",
            "deepseek-chat": "gpt-4o-mini",
            "gpt-4o-mini": "gpt-4o-mini",
        }
        return downgrade_map.get(model, "gpt-4o-mini")


# 全局 Gateway 实例
gateway = LLMGateway(config_manager=config_manager)

__all__ = [
    "LLMGateway",
    "gateway",
    "config_manager",
    "ModelConfigManager",
    "ProviderFactory",
    "CostTracker",
    "CostRecord",
    "SemanticCache",
    "BudgetController",
    "gateway_request_context",
    "budget_controller",
    "RateLimiter",
    "rate_limiter",
    "LLMResponse",
    "EmbeddingResponse",
    "RerankResponse",
    "ChatMessage",
    "CompletionUsage",
]
