"""实体多源融合 Embedding — 名称+描述+TextUnit+Claims 四源加权。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import Claim, KGEntity, TextUnit

logger = get_logger("prd2tsd.knowledge.entity_embedder")


class EntityEmbedder:
    """实体多源融合 Embedding。

    将名称、描述、关联的 TextUnit 原文、关联的 Claims 进行加权融合。
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

    def embed_entity(
        self,
        entity: KGEntity,
        text_units: list[TextUnit] | None = None,
        claims: list[Claim] | None = None,
    ) -> list[float]:
        """对实体进行多源融合 Embedding。

        加权策略：
        - 名称: 权重 0.3
        - 描述: 权重 0.3
        - TextUnit 原文: 权重 0.25
        - Claims: 权重 0.15

        Args:
            entity: 实体对象。
            text_units: 关联的 TextUnit 列表。
            claims: 关联的 Claim 列表。

        Returns:
            融合后的向量。
        """
        model = self._lazy_load_model()
        texts: list[str] = []
        weights: list[float] = []

        # 名称
        if entity.name:
            texts.append(entity.name)
            weights.append(0.3)

        # 描述
        if entity.description:
            texts.append(entity.description)
            weights.append(0.3)

        # TextUnit 原文
        if text_units:
            tu_text = " ".join(tu.text for tu in text_units if tu.text)
            if tu_text:
                texts.append(tu_text[:500])
                weights.append(0.25)

        # Claims
        if claims:
            claims_text = " ".join(c.content for c in claims if c.content)
            if claims_text:
                texts.append(claims_text[:500])
                weights.append(0.15)

        if not texts:
            return [0.0] * kn_config.embedding_dimension

        # 加权平均
        embeddings = model.encode(texts, normalize_embeddings=True)
        total_weight = sum(weights)
        if total_weight == 0:
            return embeddings[0].tolist() if len(embeddings) > 0 else [0.0] * kn_config.embedding_dimension

        weighted = sum(emb * (w / total_weight) for emb, w in zip(embeddings, weights, strict=False))
        return list(weighted)

    def embed_text_units(self, text_units: list[TextUnit]) -> list[list[float]]:
        """批量生成 TextUnit Embedding。

        Args:
            text_units: TextUnit 列表。

        Returns:
            向量列表。
        """
        model = self._lazy_load_model()
        texts = [tu.text for tu in text_units]
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]

    def embed_claims(self, claims: list[Claim]) -> list[list[float]]:
        """批量生成 Claims Embedding。

        Args:
            claims: Claim 列表。

        Returns:
            向量列表。
        """
        model = self._lazy_load_model()
        texts = [c.content for c in claims]
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]
