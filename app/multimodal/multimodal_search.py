"""多模态检索 — 以图搜图 + 文搜图 + RRF 融合。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logger import get_logger
from app.multimodal.clip_encoder import ClipEncoder
from app.multimodal.image_chunk_store import ImageChunk, ImageChunkStore, image_chunk_store

logger = get_logger("prd2tsd.multimodal_search")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算余弦相似度。

    Args:
        a: 向量 A。
        b: 向量 B。

    Returns:
        相似度（-1 ~ 1）。
    """
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class MultimodalSearchService:
    """多模态检索服务。

    支持三种检索模式：
    - 以图搜图：图片 → CLIP 视觉向量 → 向量相似度
    - 文搜图：文本 → CLIP 文本向量 → 向量相似度
    - 图文混合：RRF 融合视觉 + 文本两个 Score 列表
    """

    def __init__(
        self,
        encoder: ClipEncoder | None = None,
        store: ImageChunkStore | None = None,
    ) -> None:
        """初始化多模态检索服务。

        Args:
            encoder: CLIP 编码器。
            store: ImageChunk 存储。
        """
        self.encoder = encoder or ClipEncoder()
        self.store = store or image_chunk_store

    async def index_image(
        self,
        document_id: str,
        page_number: int,
        image_bytes: bytes,
        caption: str = "",
    ) -> ImageChunk:
        """索引一张图片（生成双向量并存储）。

        Args:
            document_id: 所属文档 ID。
            page_number: 页码。
            image_bytes: 图片数据。
            caption: 图片说明。

        Returns:
            创建的 ImageChunk。
        """
        visual_emb = await self.encoder.encode_image(image_bytes)
        text_emb = await self.encoder.encode_text(caption or "")

        chunk = ImageChunk(
            chunk_id=str(uuid.uuid4()),
            document_id=document_id,
            page_number=page_number,
            image_bytes=image_bytes,
            caption=caption,
            visual_embedding=visual_emb,
            text_embedding=text_emb,
        )
        self.store.store(chunk)
        logger.info(
            "图片已索引: doc=%s, page=%d, caption=%s",
            document_id, page_number, caption[:30] if caption else "",
        )
        return chunk

    async def search_by_image(
        self,
        image_bytes: bytes,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """以图搜图。

        Args:
            image_bytes: 查询图片。
            top_k: 返回结果数。

        Returns:
            相似 ImageChunk 列表，按相似度降序。
        """
        query_emb = await self.encoder.encode_image(image_bytes)
        return self._rank_by_embedding(query_emb, "visual", top_k)

    async def search_by_text(
        self,
        text: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """文搜图。

        Args:
            text: 查询文本。
            top_k: 返回结果数。

        Returns:
            相似 ImageChunk 列表。
        """
        query_emb = await self.encoder.encode_text(text)
        return self._rank_by_embedding(query_emb, "text", top_k)

    async def hybrid_search(
        self,
        image_bytes: bytes | None = None,
        text: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """图文混合检索（RRF 融合）。

        Args:
            image_bytes: 图片（可选）。
            text: 文本（可选）。
            top_k: 返回结果数。

        Returns:
            融合后的结果列表。
        """
        if image_bytes is None and text is None:
            return []

        visual_results: list[dict[str, Any]] = []
        text_results: list[dict[str, Any]] = []

        if image_bytes:
            visual_emb = await self.encoder.encode_image(image_bytes)
            visual_results = self._rank_by_embedding(visual_emb, "visual", top_k * 2)
        if text:
            text_emb = await self.encoder.encode_text(text)
            text_results = self._rank_by_embedding(text_emb, "text", top_k * 2)

        if not visual_results:
            return text_results[:top_k]
        if not text_results:
            return visual_results[:top_k]

        # RRF 融合
        return self._rrf_fusion(visual_results, text_results, top_k)

    def _rank_by_embedding(
        self,
        query_emb: list[float],
        emb_type: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """按向量相似度排序。

        Args:
            query_emb: 查询向量。
            emb_type: 向量类型（visual / text）。
            top_k: 返回数。

        Returns:
            排序结果。
        """
        scored: list[dict[str, Any]] = []
        for chunk in self.store._chunks.values():
            target_emb = chunk.visual_embedding if emb_type == "visual" else chunk.text_embedding
            score = _cosine_similarity(query_emb, target_emb)
            scored.append({
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "page_number": chunk.page_number,
                "caption": chunk.caption,
                "score": round(score, 4),
                "match_type": emb_type,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _rrf_fusion(
        list_a: list[dict[str, Any]],
        list_b: list[dict[str, Any]],
        top_k: int,
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """RRF（Reciprocal Rank Fusion）融合两个结果列表。

        Args:
            list_a: 结果列表 A。
            list_b: 结果列表 B。
            top_k: 返回数。
            k: RRF 常数（默认 60）。

        Returns:
            融合后的结果。
        """
        rrf_scores: dict[str, float] = {}
        items: dict[str, dict[str, Any]] = {}

        for rank, item in enumerate(list_a):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            items[cid] = item

        for rank, item in enumerate(list_b):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in items:
                items[cid] = item

        sorted_items = sorted(
            items.values(),
            key=lambda x: rrf_scores.get(x["chunk_id"], 0),
            reverse=True,
        )
        return sorted_items[:top_k]
