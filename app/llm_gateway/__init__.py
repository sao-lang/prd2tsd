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

from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

from opentelemetry import trace

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerManager
from app.core.logger import get_logger
from app.llm_gateway.budget_controller import BudgetController, budget_controller
from app.llm_gateway.cache import SemanticCache
from app.llm_gateway.capabilities.embedding import UnifiedEmbedding
from app.llm_gateway.capabilities.reranking import UnifiedReranking
from app.llm_gateway.config_manager import ModelConfigManager
from app.llm_gateway.cost_tracker import CostRecord, CostTracker
from app.llm_gateway.failover import AllProvidersUnavailableError, FailoverManager, FailoverTarget
from app.llm_gateway.guardrails import GuardrailManager
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

logger = get_logger("prd2tsd.gateway")

# 全局单例
config_manager = ModelConfigManager()


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
        """初始化 Failover 链（配置驱动）。"""
        # LLM 链：deepseek-chat → gpt-4o-mini → 本地 llama
        self.failover.configure("llm", [
            FailoverTarget(provider="deepseek", model="deepseek-chat", priority=0),
            FailoverTarget(provider="openai", model="gpt-4o-mini", priority=1),
        ])
        # Embedding 链
        self.failover.configure("embedding", [
            FailoverTarget(provider="openai", model="text-embedding-3-small", priority=0),
        ])
        logger.info("Failover 链初始化完成")

    def _init_guardrails(self) -> None:
        """注册默认护栏。"""
        from app.llm_gateway.guardrails.empty_response_guardrail import EmptyResponseGuardrail
        from app.llm_gateway.guardrails.retry_decision_guardrail import RetryDecisionGuardrail
        from app.llm_gateway.guardrails.timeout_guardrail import TimeoutGuardrail

        self.guardrails.register(PromptInjectionGuardrail())
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
        with tracer.start_as_current_span(
            f"gateway.complete.{task_type}",
            attributes={
                "task_type": task_type,
                "workspace_id": workspace_id,
                "layer": layer,
                "node": node,
            },
            kind=trace.SpanKind.CLIENT,
        ) as span:
            # ── 步骤 0: 前置护栏 ──
            guard_context = {
                "task_type": task_type,
                "workspace_id": workspace_id,
                "layer": layer,
            }
            input_results = await self.guardrails.check_input(prompt, guard_context)
            for r in input_results:
                if r.blocked:
                    span.set_attribute("guardrail_blocked", r.name)
                    logger.warning("输入被护栏拦截: %s — %s", r.name, r.reason)
                    # 护栏拦截路径也记录调用次数（避免指标低估）
                    LLM_CALL_TOTAL.labels("", layer, node).inc()
                    return LLMResponse(
                        content=f"[输入被护栏拦截: {r.reason}]",
                        model="",
                        cached=False,
                        cost=0.0,
                        input_tokens=0,
                        output_tokens=0,
                        metadata={"guardrail": r.name, "blocked": True, "reason": r.reason},
                    )

            # ── 步骤 1: 速率限制检查 ──
            rate_result = await self.rate_limiter.check(workspace_id)
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

            # ── 步骤 2: 路由解析 ──
            model_config, model_name = self.config_manager.resolve_model(task_type)

            # ── 步骤 3: 预算检查 — 自动降级 ──
            budget_check = await self.budget_controller.check_and_record(
                workspace_id, 0.0, model_name,
            )
            if budget_check.get("should_downgrade"):
                low_cost_model = self._get_low_cost_model(model_name)
                span.set_attribute("budget_downgrade", True)
                span.set_attribute("original_model", model_name)
                span.set_attribute("downgraded_model", low_cost_model)
                _provider_map = {"gpt-4o-mini": "openai", "deepseek-chat": "deepseek"}
                downgrade_provider = _provider_map.get(low_cost_model, "openai")
                model_config = self.config_manager.get_config("llm", downgrade_provider)
                model_name = low_cost_model

            # ── 指标追踪：包裹缓存命中 + 实际调用 + 成本（含失败路径） ──
            with track_llm_call(model_name, layer, node) as token_info:
                # ── 步骤 4: 语义缓存 ──
                cache_key = self.cache.make_key(prompt, task_type)
                cached = self.cache.get(cache_key)
                if cached is not None:
                    span.set_attribute("cache_hit", True)
                    return LLMResponse(
                        content=cached,
                        model=model_name,
                        cached=True,
                        cost=0.0,
                        input_tokens=0,
                        output_tokens=0,
                    )

                # ── 步骤 5: Circuit Breaker + Failover 链 ──
                pv = model_config.provider
                provider_name = pv.value if hasattr(pv, "value") else str(pv)
                cb = CircuitBreakerManager.get(f"provider:{provider_name}")

                # 如果当前 Provider 已熔断，走 Failover
                if cb and not cb.is_available:
                    logger.warning("Provider %s 已熔断，走 Failover 链", provider_name)
                    span.set_attribute("circuit_broken", True)
                    span.set_attribute("broken_provider", provider_name)

                response, model_name = await self._failover_call(
                    prompt=prompt,
                    kwargs=kwargs,
                )

                if response is None:
                    span.set_attribute("all_calls_failed", True)
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
                output_results = await self.guardrails.check_output(
                    response.content,
                    {"task_type": task_type, "model": model_name, "expected_json": expected_json},
                )
                for r in output_results:
                    if r.blocked:
                        if r.masked_text:
                            response.content = r.masked_text
                            span.set_attribute("guardrail_masked", True)
                        else:
                            response.content = f"[输出被护栏拦截: {r.reason}]"
                            span.set_attribute("guardrail_blocked", r.name)
                            break

                # ── 步骤 8: 设置缓存 / 成本 / 预算 / 速率 ──
                self.cache.set(cache_key, response.content)

                self.cost_tracker.record(
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

                # 成本指标（按实际使用模型）
                LLM_COST_TOTAL.labels(model_name).inc(response.cost)

                await self.budget_controller.check_and_record(
                    workspace_id, response.cost, model_name,
                )

                await self.rate_limiter.record(
                    workspace_id, response.input_tokens + response.output_tokens,
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
        """流式调用 LLM，逐 token 生成文本。

        保留完整链路：速率限制 → 模型路由 → 预算检查 → 追踪
        → 语义缓存(跳过) → Failover + Provider.stream_complete() → 成本记录

        Args:
            prompt: 输入提示词。
            task_type: 任务类型，用于模型路由。
            workspace_id: 工作空间 ID。
            layer: 所属层名。
            node: 所属节点名。
            **kwargs: 额外参数传递给 Provider。

        Yields:
            文本块（逐 token 或逐 chunk）。
        """
        # ── 步骤 1: 速率限制检查 ──
        rate_result = await self.rate_limiter.check(workspace_id)
        if not rate_result["allowed"]:
            yield f"[速率限制，请 {rate_result['retry_after']} 秒后重试]"
            return

        # ── 步骤 2: 路由解析 ──
        model_config, model_name = self.config_manager.resolve_model(task_type)

        # ── 步骤 3: 预算检查 — 自动降级 ──
        budget_check = await self.budget_controller.check_and_record(
            workspace_id, 0.0, model_name,
        )
        if budget_check.get("should_downgrade"):
            low_cost_model = self._get_low_cost_model(model_name)
            model_name = low_cost_model

        # ── 步骤 4: 语义缓存（流式跳过） ──

        # ── 步骤 5: Failover 链 + Provider 流式调用 ──
        full_content_chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0

        # 指标追踪：包裹流式调用（流式结束后统计 token / 成本）
        with track_llm_call(model_name, layer, node) as token_info:
            for attempt in range(3):
                try:
                    target = await self.failover.get_target("llm")
                    target_provider = target.provider
                    target_model = target.model

                    target_config = self.config_manager.get_config("llm", target_provider)
                    cb = CircuitBreakerManager.get(f"provider:{target_provider}")
                    if cb and not cb.is_available:
                        continue

                    provider = self.provider_factory.create(target_config.provider, target_config)
                    actual_model = kwargs.pop("model", target_model) or target_model

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
                        async for chunk in provider.stream_complete(
                            prompt=prompt,
                            model=actual_model,
                            **kwargs,
                        ):
                            full_content_chunks.append(chunk)
                            yield chunk

                        # ── 成本记录（流式结束后） ──
                        output_tokens = len("".join(full_content_chunks)) // 4
                        input_tokens = len(prompt) // 4
                        estimated_cost = (input_tokens * 0.00015 + output_tokens * 0.0006) / 1000

                        self.cost_tracker.record(
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

                        # 成本指标（流式按估算成本）
                        LLM_COST_TOTAL.labels(actual_model).inc(estimated_cost)

                        if workspace_id:
                            await self.budget_controller.check_and_record(
                                workspace_id, estimated_cost, actual_model,
                            )

                        span.set_attribute("input_tokens", input_tokens)
                        span.set_attribute("output_tokens", output_tokens)
                        span.set_attribute("estimated_cost", estimated_cost)

                    # 成功，退出重试
                    break

                except AllProvidersUnavailableError:
                    logger.error("流式调用: 所有 LLM Provider 均不可用")
                    yield "[所有 LLM Provider 均不可用]"
                    return
                except Exception as exc:
                    logger.warning("流式调用失败 (attempt=%d): %s", attempt, exc)
                    with suppress(Exception):
                        await self.failover.record_failure("llm", target_provider)
                    if attempt == 2:
                        logger.exception("流式调用全部重试失败: task_type=%s", task_type)
                        yield f"[流式调用出错: {exc}]"

            # 记录 token 指标
            token_info["input_tokens"] = input_tokens
            token_info["output_tokens"] = output_tokens

    async def _failover_call(
        self,
        prompt: str,
        kwargs: dict[str, Any],
    ) -> tuple[LLMResponse | None, str]:
        """执行 Circuit Breaker + Failover 链调用。

        Args:
            prompt: 输入提示词。
            kwargs: 调用参数。

        Returns:
            (LLMResponse, model_name) 或 (None, "") 全部失败。
        """
        for attempt in range(3):
            target_provider = ""
            try:
                target = await self.failover.get_target("llm")
                target_provider = target.provider
                target_model = target.model

                target_config = self.config_manager.get_config("llm", target_provider)
                target_cb = CircuitBreakerManager.get(f"provider:{target_provider}")

                if target_cb and not target_cb.is_available:
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
                    mdl = kw.pop("model", _m) or _m
                    return await provider.complete(prompt=_p, model=mdl, **kw)

                if target_cb:
                    resp = await target_cb.call(_call)
                else:
                    resp = await _call()

                return resp, target_model

            except AllProvidersUnavailableError:
                logger.error("所有 LLM Provider 均不可用")
                return (None, "")
            except Exception as e:
                logger.warning("Provider 调用失败 (attempt=%d): %s", attempt, e)
                with suppress(Exception):
                    await self.failover.record_failure("llm", target_provider)

        return (None, "")

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
        # 速率限制检查
        rate_result = await self.rate_limiter.check(workspace_id="", tokens=0)
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

        # 速率限制记录
        await self.rate_limiter.record(workspace_id="", tokens=response.input_tokens or len(texts) * 128)

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
        # 速率限制检查
        rate_result = await self.rate_limiter.check(workspace_id="", tokens=0)
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

        # 速率限制记录
        input_tokens = response.input_tokens or (len(query) + sum(len(d) for d in docs)) // 4
        await self.rate_limiter.record(workspace_id="", tokens=input_tokens)

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
gateway = LLMGateway()

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
    "budget_controller",
    "RateLimiter",
    "rate_limiter",
    "LLMResponse",
    "EmbeddingResponse",
    "RerankResponse",
    "ChatMessage",
    "CompletionUsage",
]
