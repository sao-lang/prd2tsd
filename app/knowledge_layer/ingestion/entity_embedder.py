"""实体 Embedding — API 优先，本地模型兜底。

通过 Gateway 统一调用：
  1. API 模式：gateway.embed() → OpenAI text-embedding-3-small
  2. 本地模式：SentenceTransformer（如 BAAI/bge-large-zh-v1.5）
  3. auto 模式：API 失败时自动降级到本地

实体 Embedding 策略：名称(0.5) + 描述(0.5) 加权融合。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import KGEntity

logger = get_logger("prd2tsd.knowledge.entity_embedder")


class EntityEmbedder:
    """实体 Embedding。

    API 优先，本地模型兜底。支持名称+描述双源融合。
    """

    def __init__(self) -> None:
        """初始化 Embedder。"""
        self._model_name = kn_config.embedding_model_name
        self._device = kn_config.embedding_device
        self._local_model: Any = None
        self._gateway: Any = None

    def _get_gateway(self) -> Any:
        """延迟获取 Gateway 实例。

        Returns:
            LLMGateway 实例。
        """
        if self._gateway is None:
            from app.llm_gateway import gateway
            self._gateway = gateway
        return self._gateway

    def _lazy_load_local_model(self) -> Any:
        """延迟加载本地 SentenceTransformer 模型。

        Returns:
            SentenceTransformer 模型实例，加载失败时返回 None。
        """
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("加载本地 Embedding 模型: %s (device=%s)", self._model_name, self._device)
                self._local_model = SentenceTransformer(self._model_name, device=self._device)
            except Exception as exc:
                logger.warning("本地 Embedding 模型加载失败: %s", exc)
                return None
        return self._local_model

    async def embed_text(self, text: str) -> list[float]:
        """对单段文本生成 Embedding — API 优先，本地兜底。

        Args:
            text: 输入文本。

        Returns:
            向量。
        """
        if not text.strip():
            return [0.0] * kn_config.embedding_dimension

        # API 优先
        gateway = self._get_gateway()
        try:
            resp = await gateway.embed(texts=[text], task_type="embedding")
            if resp.embeddings and len(resp.embeddings[0]) > 0:
                return resp.embeddings[0]
        except Exception as exc:
            logger.warning("API Embedding 失败，降级到本地模型: %s", exc)

        # 本地兜底
        model = self._lazy_load_local_model()
        if model is not None:
            vec = model.encode(text, normalize_embeddings=True)
            return list(vec)

        # 最终兜底：零向量
        logger.warning("Embedding 完全不可用，返回零向量")
        return [0.0] * kn_config.embedding_dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本 Embedding — API 优先，本地兜底。

        Args:
            texts: 文本列表。

        Returns:
            向量列表。
        """
        if not texts:
            return []

        # API 优先
        gateway = self._get_gateway()
        try:
            resp = await gateway.embed(texts=texts, task_type="embedding")
            if resp.embeddings and len(resp.embeddings) > 0:
                return resp.embeddings
        except Exception as exc:
            logger.warning("API 批量 Embedding 失败，降级到本地模型: %s", exc)

        # 本地兜底
        model = self._lazy_load_local_model()
        if model is not None:
            embeddings = model.encode(texts, normalize_embeddings=True)
            return [list(v) for v in embeddings]

        return [[0.0] * kn_config.embedding_dimension for _ in texts]

    async def embed_entity(self, entity: KGEntity) -> list[float]:
        """对实体进行双源融合 Embedding — API 优先，本地兜底。

        加权策略：
        - 名称: 权重 0.5
        - 描述: 权重 0.5

        Args:
            entity: 实体对象。

        Returns:
            融合后的向量。
        """
        texts: list[str] = []
        weights: list[float] = []

        if entity.name:
            texts.append(entity.name)
            weights.append(0.5)

        if entity.description:
            texts.append(entity.description)
            weights.append(0.5)

        if not texts:
            return [0.0] * kn_config.embedding_dimension

        # API 优先：批量获取所有文本的向量
        gateway = self._get_gateway()
        try:
            resp = await gateway.embed(texts=texts, task_type="embedding")
            if resp.embeddings and len(resp.embeddings) == len(texts):
                total_weight = sum(weights)
                weighted = [
                    sum(emb[d] * (w / total_weight) for emb, w in zip(resp.embeddings, weights, strict=False))
                    for d in range(len(resp.embeddings[0]))
                ]
                return weighted
        except Exception as exc:
            logger.warning("API 实体 Embedding 失败，降级到本地模型: %s", exc)

        # 本地兜底
        model = self._lazy_load_local_model()
        if model is not None:
            embeddings = model.encode(texts, normalize_embeddings=True)
            total_weight = sum(weights)
            weighted = sum(
                emb * (w / total_weight) for emb, w in zip(embeddings, weights, strict=False)
            )
            return list(weighted)

        return [0.0] * kn_config.embedding_dimension
