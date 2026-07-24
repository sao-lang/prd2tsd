"""统一 Rerank 能力 — API 优先，本地模型兜底。

策略：
  1. API 模式：通过 Gateway 的 ProviderFactory 调用 Cohere Rerank API
  2. 本地模式：使用 HuggingFace Cross-encoder（如 BAAI/bge-reranker-v2-m3）
  3. 自动降级：API 不可用时自动回退到本地模型

配置（环境变量 / .env / 代码默认值）：
  MODEL_CONFIG__RERANK__COHERE__API_KEY
  MODEL_CONFIG__RERANK__COHERE__BASE_URL
  MODEL_CONFIG__RERANK__COHERE__DEFAULT_MODEL
  RERANK_MODE=auto|api|local
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.llm_gateway.models import RerankResponse

logger = get_logger("prd2tsd.gateway.reranking")


class UnifiedReranking:
    """统一 Rerank 能力。

    API 优先，本地模型兜底。支持运行时切换模式。
    """

    def __init__(
        self,
        config_manager: Any | None = None,
        provider_factory: Any | None = None,
        mode: str = "auto",
    ) -> None:
        """初始化统一 Rerank。

        Args:
            config_manager: ModelConfigManager 实例。
            provider_factory: ProviderFactory 实例。
            mode: 运行模式（auto/api/local）。
        """
        self._config_manager = config_manager
        self._provider_factory = provider_factory
        self._mode = mode
        self._local_model: Any = None
        self._local_tokenizer: Any = None
        self._local_model_name: str = "BAAI/bge-reranker-v2-m3"

    async def rerank(
        self,
        query: str,
        docs: list[str],
        task_type: str = "rerank",
        mode: str | None = None,
        top_k: int | None = None,
        **kwargs: Any,
    ) -> RerankResponse:
        """对文档进行重排序。

        Args:
            query: 查询文本。
            docs: 文档列表。
            task_type: 任务类型。
            mode: 临时覆盖运行模式。
            top_k: 返回前 k 个结果。
            **kwargs: 额外参数。

        Returns:
            RerankResponse。
        """
        effective_mode = mode or self._mode

        # API 优先
        if effective_mode in ("auto", "api"):
            try:
                return await self._api_rerank(query, docs, task_type, top_k, **kwargs)
            except Exception as exc:
                if effective_mode == "api":
                    logger.warning("API Rerank 失败（api 模式无兜底）: %s", exc)
                    raise
                logger.warning("API Rerank 失败，降级到本地模型: %s", exc)

        # 本地兜底
        return self._local_rerank(query, docs, top_k)

    async def _api_rerank(
        self,
        query: str,
        docs: list[str],
        task_type: str,
        top_k: int | None,
        **kwargs: Any,
    ) -> RerankResponse:
        """通过 API Provider 重排序。

        Args:
            query: 查询文本。
            docs: 文档列表。
            task_type: 任务类型。
            top_k: 返回数量。
            **kwargs: 额外参数。

        Returns:
            RerankResponse。

        Raises:
            Exception: API 调用失败时抛出。
        """
        if self._config_manager is None or self._provider_factory is None:
            raise RuntimeError("API Rerank 不可用：未配置 config_manager/provider_factory")

        model_config, model_name = self._config_manager.resolve_model(task_type)
        provider = self._provider_factory.create(model_config.provider, model_config)
        response = await provider.rerank(
            query=query,
            docs=docs,
            model=kwargs.pop("model", model_name),
            top_n=top_k,
            **kwargs,
        )
        logger.info(
            "API Rerank 完成: model=%s, docs=%d",
            model_name, len(docs),
        )
        return response

    def _local_rerank(
        self,
        query: str,
        docs: list[str],
        top_k: int | None,
    ) -> RerankResponse:
        """通过本地 Cross-encoder 重排序。

        Args:
            query: 查询文本。
            docs: 文档列表。
            top_k: 返回数量。

        Returns:
            RerankResponse。
        """
        model, tokenizer = self._get_local_model()

        if model is not None and tokenizer is not None:
            import torch

            pairs = [(query, doc[:512]) for doc in docs]
            inputs = tokenizer(
                pairs, padding=True, truncation=True, max_length=512, return_tensors="pt",
            )
            with torch.no_grad():
                outputs = model(**inputs)
                scores = outputs.logits.squeeze(-1).tolist()

            if isinstance(scores, float):
                scores = [scores]

            # 按分数降序排列
            indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            if top_k is not None:
                indexed = indexed[:top_k]

            indices = [i for i, _ in indexed]
            sorted_scores = [s for _, s in indexed]

            logger.info(
                "本地 Rerank 完成: model=%s, docs=%d, top_k=%s",
                self._local_model_name, len(docs), top_k or "all",
            )
            return RerankResponse(
                scores=sorted_scores,
                indices=indices,
                model=f"local:{self._local_model_name}",
            )

        # 无模型：按原始顺序返回
        logger.warning("本地 Rerank 模型未加载，返回原始顺序")
        k = top_k or len(docs)
        return RerankResponse(
            scores=[1.0 - i * 0.01 for i in range(min(k, len(docs)))],
            indices=list(range(min(k, len(docs)))),
            model="fallback:identity",
        )

    def _get_local_model(self) -> tuple[Any, Any]:
        """延迟加载本地 Cross-encoder 模型。

        Returns:
            (model, tokenizer) 元组。
        """
        if self._local_model is None:
            try:
                from transformers import (
                    AutoModelForSequenceClassification,
                    AutoTokenizer,
                )

                logger.info("加载本地 Rerank 模型: %s", self._local_model_name)
                self._local_tokenizer = AutoTokenizer.from_pretrained(self._local_model_name)
                self._local_model = AutoModelForSequenceClassification.from_pretrained(
                    self._local_model_name,
                )
            except Exception as exc:
                logger.warning("本地 Rerank 模型加载失败: %s", exc)
                return None, None

        return self._local_model, self._local_tokenizer

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
        logger.info("Rerank 模式已切换: %s", value)
