"""LLM Gateway — 统一模型调用门面。

所有后续 Agent Layer 通过此模块调用 LLM/Embedding/Rerank 等模型。
"""

from app.llm_gateway.cache import SemanticCache
from app.llm_gateway.config_manager import ModelConfigManager
from app.llm_gateway.cost_tracker import CostTracker
from app.llm_gateway.models import (
    ChatMessage,
    CompletionUsage,
    EmbeddingResponse,
    LLMResponse,
    RerankResponse,
)
from app.llm_gateway.providers import ProviderFactory
from app.llm_gateway.router import ModelRouter

# 全局单例
config_manager = ModelConfigManager()


class LLMGateway:
    """LLM Gateway 门面类 — 统一对外接口。

    组装 Provider + Router + CostTracker + Cache，提供 complete/embed/rerank 等方法。
    """

    def __init__(
        self,
        config_manager: ModelConfigManager | None = None,
        router: ModelRouter | None = None,
        provider_factory: ProviderFactory | None = None,
        cost_tracker: CostTracker | None = None,
        cache: SemanticCache | None = None,
    ) -> None:
        """初始化 LLM Gateway。

        Args:
            config_manager: 模型配置管理器。为 None 时使用全局单例。
            router: 模型路由器。为 None 时自动创建。
            provider_factory: Provider 工厂。为 None 时自动创建。
            cost_tracker: 成本追踪器。为 None 时自动创建。
            cache: 语义缓存。为 None 时自动创建。
        """
        self.config_manager = config_manager or ModelConfigManager()
        self.router = router or ModelRouter(self.config_manager)
        self.provider_factory = provider_factory or ProviderFactory()
        self.cost_tracker = cost_tracker or CostTracker()
        self.cache = cache or SemanticCache()

    async def complete(
        self,
        prompt: str,
        task_type: str = "default",
        workspace_id: str = "",
        **kwargs: dict,
    ) -> LLMResponse:
        """调用 LLM 生成文本。

        Args:
            prompt: 输入提示词。
            task_type: 任务类型，用于模型路由。
            workspace_id: 工作空间 ID。
            **kwargs: 额外参数传递给 Provider。

        Returns:
            LLMResponse 包含生成结果、成本、模型等信息。
        """
        # 1. 路由解析
        model_config, model_name = self.config_manager.resolve_model(task_type)

        # 2. 检查缓存
        cache_key = self.cache.make_key(prompt, task_type)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return LLMResponse(
                content=cached,
                model=model_name,
                cached=True,
                cost=0.0,
                input_tokens=0,
                output_tokens=0,
            )

        # 3. 创建 Provider 并调用
        provider = self.provider_factory.create(model_config.provider, model_config)
        response = await provider.complete(
            prompt=prompt,
            model=kwargs.pop("model", model_name),
            **kwargs,
        )

        # 4. 设置缓存
        self.cache.set(cache_key, response.content)

        # 5. 记录成本
        self.cost_tracker.record(
            model=model_name,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        return response

    async def embed(
        self,
        texts: list[str],
        task_type: str = "embedding",
        **kwargs: dict,
    ) -> EmbeddingResponse:
        """调用 Embedding 模型。

        Args:
            texts: 需要向量化的文本列表。
            task_type: 任务类型。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse 包含向量和成本信息。
        """
        model_config, model_name = self.config_manager.resolve_model(task_type)
        provider = self.provider_factory.create(model_config.provider, model_config)
        response = await provider.embed(texts=texts, model=kwargs.pop("model", model_name), **kwargs)
        self.cost_tracker.record(model=model_name, input_tokens=response.input_tokens, output_tokens=0)
        return response

    async def rerank(
        self,
        query: str,
        docs: list[str],
        task_type: str = "rerank",
        **kwargs: dict,
    ) -> RerankResponse:
        """调用 Rerank 模型。

        Args:
            query: 查询文本。
            docs: 需要重排序的文档列表。
            task_type: 任务类型。
            **kwargs: 额外参数。

        Returns:
            RerankResponse 包含排序后的文档和成本信息。
        """
        model_config, model_name = self.config_manager.resolve_model(task_type)
        provider = self.provider_factory.create(model_config.provider, model_config)
        response = await provider.rerank(
            query=query, docs=docs, model=kwargs.pop("model", model_name), **kwargs
        )
        self.cost_tracker.record(model=model_name, input_tokens=response.input_tokens, output_tokens=0)
        return response


# 全局 Gateway 实例
gateway = LLMGateway()

__all__ = [
    "LLMGateway",
    "gateway",
    "config_manager",
    "ModelConfigManager",
    "ModelRouter",
    "ProviderFactory",
    "CostTracker",
    "SemanticCache",
    "LLMResponse",
    "EmbeddingResponse",
    "RerankResponse",
    "ChatMessage",
    "CompletionUsage",
]
