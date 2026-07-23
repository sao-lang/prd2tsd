"""知识层 API 路由 — 知识图谱构建和检索。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.auth.deps import get_current_user
from app.core.logger import get_logger
from app.knowledge_layer.models import BuildStats, RetrievalContext
from app.knowledge_layer.pipeline import KnowledgeGraphBuilder, RetrievalPipeline
from app.models.user import User

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
logger = get_logger("prd2tsd.knowledge.routes")


@router.post("/build", response_model=BuildStats)
async def build_from_document(
    file: UploadFile,
    workspace_id: str = "",
    current_user: User = Depends(get_current_user),
) -> BuildStats:
    """上传文档并构建知识图谱。

    Args:
        file: 上传的 .md 文件。
        workspace_id: 工作空间 ID。
        current_user: 当前用户。

    Returns:
        构建统计。

    Raises:
        HTTPException: 文件格式不支持或构建失败时抛出。
    """
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持 .md 文件")

    # 保存上传文件到临时目录
    tmp_dir = Path(tempfile.mkdtemp(prefix="kg_"))
    tmp_path = tmp_dir / file.filename
    content = await file.read()
    tmp_path.write_bytes(content)

    try:
        builder = KnowledgeGraphBuilder()
        stats = await builder.build_from_document(str(tmp_path), workspace_id=workspace_id)
        logger.info(
            "知识图谱构建完成: file=%s, entities=%d, relations=%d",
            file.filename,
            stats.entities,
            stats.relations,
        )
        return stats
    except Exception as e:
        logger.error("知识图谱构建失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"知识图谱构建失败: {str(e)}") from e
    finally:
        # 清理临时文件
        if tmp_path.exists():
            tmp_path.unlink()
        if tmp_dir.exists():
            tmp_dir.rmdir()


@router.post("/build-from-path", response_model=BuildStats)
async def build_from_path(
    file_path: str,
    workspace_id: str = "",
    current_user: User = Depends(get_current_user),
) -> BuildStats:
    """从服务器文件路径构建知识图谱。

    Args:
        file_path: 文件路径。
        workspace_id: 工作空间 ID。
        current_user: 当前用户。

    Returns:
        构建统计。
    """
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

    builder = KnowledgeGraphBuilder()
    try:
        stats = await builder.build_from_document(file_path, workspace_id=workspace_id)
        return stats
    except Exception as e:
        logger.error("知识图谱构建失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"知识图谱构建失败: {str(e)}") from e


@router.post("/search", response_model=RetrievalContext)
async def search_knowledge(
    query: str,
    mode: str = "hybrid",
    top_k: int = 10,
    workspace_id: str = "",
    current_user: User = Depends(get_current_user),
) -> RetrievalContext:
    """检索知识图谱。

    Args:
        query: 搜索查询。
        mode: 检索模式（local / global / hybrid）。
        top_k: 返回结果数。
        workspace_id: 工作空间 ID。
        current_user: 当前用户。

    Returns:
        检索上下文。
    """
    pipeline = RetrievalPipeline()
    try:
        context = await pipeline.retrieve(
            query=query,
            mode=mode,
            top_k=top_k,
            workspace_id=workspace_id,
        )
        return context
    except Exception as e:
        logger.error("知识检索失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"知识检索失败: {str(e)}") from e
