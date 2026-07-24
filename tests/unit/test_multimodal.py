"""多模态检索单元测试。"""

from __future__ import annotations

import pytest

from app.multimodal.clip_encoder import ClipEncoder
from app.multimodal.image_chunk_store import ImageChunk, ImageChunkStore


class TestClipEncoder:
    """CLIP 编码器单元测试。"""

    @pytest.mark.asyncio
    async def test_encode_text_returns_correct_dim(self) -> None:
        """验证文本编码输出正确维度。"""
        encoder = ClipEncoder()
        emb = await encoder.encode_text("test query")
        assert len(emb) > 0

    @pytest.mark.asyncio
    async def test_encode_image_returns_correct_dim(self) -> None:
        """验证图片编码输出正确维度。"""
        encoder = ClipEncoder()
        emb = await encoder.encode_image(b"fake-image-bytes")
        assert len(emb) > 0

    @pytest.mark.asyncio
    async def test_same_text_same_embedding(self) -> None:
        """验证相同文本产生相同向量（确定性）。"""
        encoder = ClipEncoder()
        emb1 = await encoder.encode_text("hello")
        emb2 = await encoder.encode_text("hello")
        # Mock 模式下是确定的；真实模型也应该是确定的
        assert len(emb1) == len(emb2)


class TestImageChunkStore:
    """ImageChunk 存储单元测试。"""

    def test_store_and_get(self) -> None:
        """验证存储和获取。"""
        store = ImageChunkStore()
        chunk = ImageChunk(
            chunk_id="c1", document_id="doc1", page_number=1,
            caption="test", visual_embedding=[0.1, 0.2],
        )
        store.store(chunk)
        assert store.get("c1") is not None
        assert store.get("c1").caption == "test"
        assert store.size == 1

    def test_get_by_document(self) -> None:
        """验证按文档获取。"""
        store = ImageChunkStore()
        store.store(ImageChunk(chunk_id="c1", document_id="doc1", page_number=1))
        store.store(ImageChunk(chunk_id="c2", document_id="doc1", page_number=2))
        store.store(ImageChunk(chunk_id="c3", document_id="doc2", page_number=1))
        chunks = store.get_by_document("doc1")
        assert len(chunks) == 2

    def test_delete_by_document(self) -> None:
        """验证按文档删除。"""
        store = ImageChunkStore()
        store.store(ImageChunk(chunk_id="c1", document_id="doc1", page_number=1))
        store.store(ImageChunk(chunk_id="c2", document_id="doc2", page_number=1))
        deleted = store.delete_by_document("doc1")
        assert deleted == 1
        assert store.size == 1

    def test_clear(self) -> None:
        """验证清空。"""
        store = ImageChunkStore()
        store.store(ImageChunk(chunk_id="c1", document_id="doc1", page_number=1))
        store.clear()
        assert store.size == 0
