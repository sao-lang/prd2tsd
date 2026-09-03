"""知识构建 API 多格式入口测试。"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.api.routes.knowledge import build_from_document
from app.knowledge_layer.models import BuildStats


@pytest.mark.asyncio
async def test_build_route_accepts_image_and_uses_bytes_pipeline() -> None:
    """直接知识构建端点应把图片字节交给 OCR 所在的 build_from_bytes。"""
    upload = UploadFile(filename="architecture.png", file=BytesIO(b"png-bytes"))
    builder = MagicMock()
    builder.build_from_bytes = AsyncMock(return_value=BuildStats(entities=1, chunks=1, file_path="architecture.png"))

    with patch("app.api.routes.knowledge.KnowledgeGraphBuilder", return_value=builder):
        result = await build_from_document(upload, workspace_id="ws-1", current_user=MagicMock())

    assert result.entities == 1
    builder.build_from_bytes.assert_awaited_once_with(
        b"png-bytes",
        "architecture.png",
        workspace_id="ws-1",
    )


@pytest.mark.asyncio
async def test_build_route_rejects_unsupported_extension() -> None:
    """不支持的扩展名在构造 Builder 前被拒绝。"""
    upload = UploadFile(filename="malware.exe", file=BytesIO(b"payload"))

    with pytest.raises(HTTPException) as error:
        await build_from_document(upload, current_user=MagicMock())

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_build_route_rejects_oversized_file() -> None:
    """知识构建端点保留与文档上传一致的体积边界。"""
    upload = UploadFile(filename="large.png", file=BytesIO(b"123"))

    with (
        patch("app.api.routes.knowledge.MAX_KNOWLEDGE_FILE_SIZE", 2),
        pytest.raises(HTTPException) as error,
    ):
        await build_from_document(upload, current_user=MagicMock())

    assert error.value.status_code == 413
