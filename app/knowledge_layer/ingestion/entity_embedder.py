"""实体 Embedding — 名称 + 描述 双源融合。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import KGEntity

logger = get_logger("prd2tsd.knowledge.entity_embedder")


class EntityEmbedder:
    """实体 Embedding。

    将名称和描述进行加权融合，生成实体的语义向量。
    """

    def __init__(self) -> None:
        """初始化 Embedder。"""
        self._model_name = kn_config.embedding_model_name
        self._device = kn_config.embedding_device
        self._model: Any = None

    def _lazy_load_model(self) -> Any:
        """延迟加载 Embedding 模型。

        Returns:
            SentenceTransformer 模型实例。
        """
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("加载 Embedding 模型: %s (device=%s)", self._model_name, self._device)
            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """对单段文本生成 Embedding。

        Args:
            text: 输入文本。

        Returns:
            向量（1024 维）。
        """
        if not text.strip():
            return [0.0] * kn_config.embedding_dimension
        model = self._lazy_load_model()
        vec = model.encode(text, normalize_embeddings=True)
        return list(vec)

    def embed_entity(self, entity: KGEntity) -> list[float]:
        """对实体进行双源融合 Embedding。

        加权策略：
        - 名称: 权重 0.5
        - 描述: 权重 0.5

        Args:
            entity: 实体对象。

        Returns:
            融合后的向量。
        """
        model = self._lazy_load_model()
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

        embeddings = model.encode(texts, normalize_embeddings=True)
        total_weight = sum(weights)

        weighted = sum(emb * (w / total_weight) for emb, w in zip(embeddings, weights, strict=False))
        return list(weighted)
