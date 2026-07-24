"""统一 Embedding 能力 — API 优先，本地模型兜底。

策略：
  1. API 模式：通过 Gateway 的 ProviderFactory 调用 OpenAI text-embedding-3-small
  2. 本地模式：使用 SentenceTransformer 加载本地模型（如 BAAI/bge-large-zh-v1.5）
  3. 自动降级：API 不可用时自动回退到本地模型

配置（环境变量 / .env / 代码默认值）：
  MODEL_CONFIG__EMBEDDING__OPENAI__API_KEY
  MODEL_CONFIG__EMBEDDING__OPENAI__BASE_URL
  MODEL_CONFIG__EMBEDDING__OPENAI__DEFAULT_MODEL
  EMBEDDING_MODE=auto|api|local    （auto=API优先，local=仅本地）
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.llm_gateway.models import EmbeddingResponse

logger = get_logger("prd2tsd.gateway.embedding")


class UnifiedEmbedding:
    """统一 Embedding 能力。

    API 优先，本地模型兜底。支持运行时切换模式。
    """

    def __init__(
        self,
        config_manager: Any | None = None,
        provider_factory: Any | None = None,
        mode: str = "auto",
    ) -> None:
        """初始化统一 Embedding。

        Args:
            config_manager: ModelConfigManager 实例，用于获取 API 配置。
            provider_factory: ProviderFactory 实例，用于创建 API Provider。
            mode: 运行模式（auto/api/local）。
        """
        self._config_manager = config_manager
        self._provider_factory = provider_factory
        self._mode = mode
        self._local_model: Any = None
        self._local_model_name: str = "BAAI/bge-large-zh-v1.5"
        self._local_dimension: int = 1024

    async def embed(
        self,
        texts: list[str],
        task_type: str = "embedding",
        mode: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """生成文本向量。

        Args:
            texts: 文本列表。
            task_type: 任务类型（传递给 Gateway 路由）。
            mode: 临时覆盖运行模式（auto/api/local）。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。
        """
        effective_mode = mode or self._mode

        # API 优先（auto 或 api 模式）
        if effective_mode in ("auto", "api"):
            try:
                return await self._api_embed(texts, task_type, **kwargs)
            except Exception as exc:
                if effective_mode == "api":
                    logger.warning("API Embedding 失败（api 模式无兜底）: %s", exc)
                    raise
                logger.warning("API Embedding 失败，降级到本地模型: %s", exc)

        # 本地兜底（auto 模式失败时 或 local 模式）
        return self._local_embed(texts)

    async def _api_embed(
        self,
        texts: list[str],
        task_type: str,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """通过 API Provider 生成向量。

        Args:
            texts: 文本列表。
            task_type: 任务类型。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。

        Raises:
            Exception: API 调用失败时抛出。
        """
        if self._config_manager is None or self._provider_factory is None:
            raise RuntimeError("API Embedding 不可用：未配置 config_manager/provider_factory")

        model_config, model_name = self._config_manager.resolve_model(task_type)
        provider = self._provider_factory.create(model_config.provider, model_config)
        response = await provider.embed(
            texts=texts,
            model=kwargs.pop("model", model_name),
            **kwargs,
        )
        logger.info(
            "API Embedding 完成: model=%s, texts=%d, dim=%d",
            model_name, len(texts), len(response.embeddings[0]) if response.embeddings else 0,
        )
        return response

    def _local_embed(self, texts: list[str]) -> EmbeddingResponse:
        """通过本地 SentenceTransformer 生成向量。

        Args:
            texts: 文本列表。

        Returns:
            EmbeddingResponse。
        """
        model = self._get_local_model()
        embeddings = model.encode(texts, normalize_embeddings=True).tolist()
        logger.info(
            "本地 Embedding 完成: model=%s, texts=%d, dim=%d",
            self._local_model_name, len(texts), len(embeddings[0]) if embeddings else 0,
        )
        return EmbeddingResponse(
            embeddings=embeddings,
            model=f"local:{self._local_model_name}",
        )

    def _get_local_model(self) -> Any:
        """延迟加载本地 SentenceTransformer 模型。

        Returns:
            SentenceTransformer 实例。
        """
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("加载本地 Embedding 模型: %s", self._local_model_name)
            self._local_model = SentenceTransformer(self._local_model_name, device="cpu")
        return self._local_model

    @property
    def mode(self) -> str:
        """当前运行模式。"""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        """设置运行模式。

        Args:
            value: auto / api / local。
        """
        if value not in ("auto", "api", "local"):
            raise ValueError(f"无效模式: {value}，可选 auto/api/local")
        self._mode = value
        logger.info("Embedding 模式已切换: %s", value)
