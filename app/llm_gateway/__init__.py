"""LLM Gateway — 统一模型调用门面。

所有 Agent Layer 通过此模块调用 LLM/Embedding/Rerank/ImageEncode 等模型。
集成预算控制、速率限制、可观测性追踪和 本地模型兜底（Capabilities 层）。
"""

from __future__ import annotations

from typing import Any

from app.llm_gateway.budget_controller import BudgetController, budget_controller
from app.llm_gateway.cache import SemanticCache
from app.llm_gateway.capabilities.embedding import UnifiedEmbedding
from app.llm_gateway.capabilities.image_encoder import UnifiedImageEncoder
from app.llm_gateway.capabilities.reranking import UnifiedReranking
from app.llm_gateway.config_manager import ModelConfigManager
from app.llm_gateway.cost_tracker import CostRecord, CostTracker
from app.llm_gateway.models import (
    ChatMessage,
    CompletionUsage,
    EmbeddingResponse,
    LLMResponse,
    RerankResponse,
)
from app.llm_gateway.providers import ProviderFactory
from app.llm_gateway.rate_limiter import RateLimiter, rate_limiter
from app.observability.metrics import track_llm_call
from app.observability.tracing import tracer

# 全局单例
config_manager = ModelConfigManager()


class LLMGateway:
    """LLM Gateway 门面类 — 统一对外接口。

    组装 Provider + Router + CostTracker + Cache + BudgetController + RateLimiter，
    提供 complete/embed/rerank/encode_image 等方法。

    Capabilities 层实现"API 优先，本地模型兜底"策略：
      - embed       → UnifiedEmbedding: OpenAI API → SentenceTransformer
      - rerank      → UnifiedReranking: Cohere API → BGE Cross-encoder
      - encode_image → UnifiedImageEncoder: (预留) → CLIP
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
        image_encoder: UnifiedImageEncoder | None = None,
    ) -> None:
        """初始化 LLM Gateway。

        Args:
            config_manager: 模型配置管理器。为 None 时使用全局单例。
            provider_factory: Provider 工厂。为 None 时自动创建。
            cost_tracker: 成本追踪器。为 None 时自动创建。
            cache: 语义缓存。为 None 时自动创建。
            budget_controller: 预算控制器。为 None 时使用全局单例。
            rate_limiter: 速率限制器。为 None 时使用全局单例。
            embedding: UnifiedEmbedding 实例。为 None 时自动创建。
            reranking: UnifiedReranking 实例。为 None 时自动创建。
            image_encoder: UnifiedImageEncoder 实例。为 None 时自动创建。
        """
        self.config_manager = config_manager or ModelConfigManager()
        self.provider_factory = provider_factory or ProviderFactory()
        self.cost_tracker = cost_tracker or CostTracker()
        self.cache = cache or SemanticCache()
        self.budget_controller = budget_controller or BudgetController()
        self.rate_limiter = rate_limiter or RateLimiter()
        # Capabilities（API 优先，本地模型兜底）
        self.embedding_cap = embedding or UnifiedEmbedding(
            config_manager=self.config_manager,
            provider_factory=self.provider_factory,
        )
        self.reranking_cap = reranking or UnifiedReranking(
            config_manager=self.config_manager,
            provider_factory=self.provider_factory,
        )
        self.image_encoder_cap = image_encoder or UnifiedImageEncoder()

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

        Block E 增强链路：
        1. 速率限制检查
        2. 模型路由
        3. 预算检查（超限告警/自动降级）
        4. 语义缓存检查（命中直接返回）
        5. 追踪 + Prometheus 指标 + 实际 LLM 调用
        6. 设置缓存
        7. 成本记录
        8. 预算记录
        9. 速率限制记录

        Args:
            prompt: 输入提示词。
            task_type: 任务类型，用于模型路由。
            workspace_id: 工作空间 ID。
            layer: 所属层名（analysis/planning/generation/evaluation）。
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
            kind=1,  # SpanKind.CLIENT
        ) as span:
            # 1. 速率限制检查
            rate_result = await self.rate_limiter.check(workspace_id)
            if not rate_result["allowed"]:
                span.set_attribute("rate_limited", True)
                span.set_attribute("retry_after", rate_result["retry_after"])
                return LLMResponse(
                    content="",
                    model=model_name,
                    cached=False,
                    cost=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    metadata={"error": "rate_limited", "retry_after": rate_result["retry_after"]},
                )

            # 2. 路由解析
            model_config, model_name = self.config_manager.resolve_model(task_type)

            # 3. 预算检查 — 如需降级切换模型和 Provider 配置
            budget_check = await self.budget_controller.check_and_record(
                workspace_id, 0.0, model_name,
            )
            if budget_check.get("should_downgrade"):
                low_cost_model = self._get_low_cost_model(model_name)
                span.set_attribute("budget_downgrade", True)
                span.set_attribute("original_model", model_name)
                span.set_attribute("downgraded_model", low_cost_model)
                # 降级时同时切换 Provider 配置（如 deepseek-chat→gpt-4o-mini 需换到 OpenAI）
                _provider_map = {"gpt-4o-mini": "openai", "deepseek-chat": "deepseek"}
                downgrade_provider = _provider_map.get(low_cost_model, "openai")
                model_config = self.config_manager.get_config("llm", downgrade_provider)
                model_name = low_cost_model

            # 4. 检查缓存
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

            # 5. 追踪 LLM 调用
            with track_llm_call(model=model_name, layer=layer, node=node) as token_info:
                provider = self.provider_factory.create(model_config.provider, model_config)
                response = await provider.complete(
                    prompt=prompt,
                    model=kwargs.pop("model", model_name) or model_name,
                    **kwargs,
                )
                token_info["input_tokens"] = response.input_tokens
                token_info["output_tokens"] = response.output_tokens

            # 6. 设置缓存
            self.cache.set(cache_key, response.content)

            # 7. 记录成本
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

            # 8. 预算记录实际成本
            await self.budget_controller.check_and_record(
                workspace_id, response.cost, model_name,
            )

            # 9. 记录速率限制
            await self.rate_limiter.record(
                workspace_id, response.input_tokens + response.output_tokens,
            )

            span.set_attribute("model", model_name)
            span.set_attribute("input_tokens", response.input_tokens)
            span.set_attribute("output_tokens", response.output_tokens)
            span.set_attribute("cost", response.cost)

            return response

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

    async def encode_image(
        self,
        image_bytes: bytes,
        mode: str | None = None,
    ) -> list[float]:
        """统一图片编码 — API 优先（预留），本地 CLIP 模型兜底。

        通过 UnifiedImageEncoder Capability 执行：
          1. API 模式：预留（未来接入多模态 API）
          2. 本地模式：CLIP (openai/clip-vit-base-patch32)
          3. auto 模式：API 失败时自动降级到本地

        Args:
            image_bytes: 图片字节数据。
            mode: 临时覆盖模式（auto/api/local）。

        Returns:
            512 维视觉向量。
        """
        return await self.image_encoder_cap.encode_image(image_bytes, mode=mode)

    async def encode_text(
        self,
        text: str,
        mode: str | None = None,
    ) -> list[float]:
        """统一文本编码（CLIP 文本空间）— API 优先（预留），本地 CLIP 模型兜底。

        通过 UnifiedImageEncoder Capability 执行，与 encode_image 共享语义空间。

        Args:
            text: 输入文本。
            mode: 临时覆盖模式（auto/api/local）。

        Returns:
            512 维文本向量。
        """
        return await self.image_encoder_cap.encode_text(text, mode=mode)

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
