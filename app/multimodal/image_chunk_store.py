"""ImageChunk 存储 — 双向量（visual_emb + text_emb）存储。"""

from __future__ import annotations

import time

from app.core.logger import get_logger

logger = get_logger("prd2tsd.image_chunk_store")


class ImageChunk:
    """图片块 — 含双向量和元数据。"""

    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        page_number: int,
        image_bytes: bytes | None = None,
        caption: str = "",
        visual_embedding: list[float] | None = None,
        text_embedding: list[float] | None = None,
    ) -> None:
        """初始化图片块。

        Args:
            chunk_id: 块 ID。
            document_id: 所属文档 ID。
            page_number: 页码。
            image_bytes: 图片字节（可选）。
            caption: 图片说明。
            visual_embedding: 视觉向量（768d）。
            text_embedding: 文本向量（768d）。
        """
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.page_number = page_number
        self.image_bytes = image_bytes
        self.caption = caption
        self.visual_embedding = visual_embedding or []
        self.text_embedding = text_embedding or []
        self.created_at = time.time()


class ImageChunkStore:
    """ImageChunk 存储。

    内存存储，按 document_id 索引。
    生产环境建议使用 PGVector 或专门的向量数据库。
    """

    def __init__(self) -> None:
        """初始化存储。"""
        self._chunks: dict[str, ImageChunk] = {}
        self._doc_index: dict[str, list[str]] = {}  # document_id → [chunk_id]

    def store(self, chunk: ImageChunk) -> None:
        """存储一个 ImageChunk。

        Args:
            chunk: 图片块实例。
        """
        self._chunks[chunk.chunk_id] = chunk
        if chunk.document_id not in self._doc_index:
            self._doc_index[chunk.document_id] = []
        self._doc_index[chunk.document_id].append(chunk.chunk_id)

    def get(self, chunk_id: str) -> ImageChunk | None:
        """获取单个 ImageChunk。

        Args:
            chunk_id: 块 ID。

        Returns:
            ImageChunk 或 None。
        """
        return self._chunks.get(chunk_id)

    def get_by_document(self, document_id: str) -> list[ImageChunk]:
        """获取文档下的所有 ImageChunk。

        Args:
            document_id: 文档 ID。

        Returns:
            ImageChunk 列表。
        """
        chunk_ids = self._doc_index.get(document_id, [])
        return [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]

    def delete_by_document(self, document_id: str) -> int:
        """删除文档的所有 ImageChunk。

        Args:
            document_id: 文档 ID。

        Returns:
            删除的块数。
        """
        chunk_ids = self._doc_index.pop(document_id, [])
        count = 0
        for cid in chunk_ids:
            if cid in self._chunks:
                del self._chunks[cid]
                count += 1
        return count

    @property
    def size(self) -> int:
        """当前存储的 ImageChunk 总数。

        Returns:
            块数。
        """
        return len(self._chunks)

    def clear(self) -> None:
        """清空所有数据。"""
        self._chunks.clear()
        self._doc_index.clear()


# 全局单例
image_chunk_store = ImageChunkStore()
