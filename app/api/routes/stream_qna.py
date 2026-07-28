"""SSE 流式 Q&A 路由 — 知识检索 + LLM 流式回答。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_gateway
from app.api.schemas.streaming import StreamQnARequest
from app.auth.deps import get_current_user
from app.llm_gateway import LLMGateway
from app.models.user import User
from app.streaming.models import SseEvent

router = APIRouter(prefix="/api/v1", tags=["streaming"])


@router.post("/qna/stream")
async def stream_qna(
    req: StreamQnARequest,
    current_user: User = Depends(get_current_user),
    gateway: LLMGateway = Depends(get_gateway),
) -> StreamingResponse:
    """流式 Q&A — 知识检索 + LLM 流式回答。

    1. 知识检索阶段 → 推送 qna.status
    2. LLM 流式生成 → 逐 chunk 推送 qna.chunk
    3. 完成 → 推送 done

    Args:
        req: 流式 Q&A 请求体。
        current_user: 当前用户。
        gateway: LLM Gateway 实例。

    Returns:
        StreamingResponse (text/event-stream)。
    """
    query = req.query
    workspace_id = req.workspace_id

    async def event_generator() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流。"""
        try:
            # 阶段 1: 知识检索
            yield SseEvent(
                type="qna.status",
                payload={
                    "phase": "retrieving",
                    "message": "正在检索知识图谱...",
                },
            ).to_sse_line()

            # 尝试知识检索（如果可用）
            context = ""
            try:
                from app.knowledge_layer.pipeline import RetrievalPipeline

                pipeline = RetrievalPipeline()
                retrieval_result = await pipeline.retrieve(
                    query=query,
                    workspace_id=workspace_id,
                    top_k=5,
                )
                # 从 RetrievalContext Pydantic 模型提取上下文
                context_parts: list[str] = []
                if retrieval_result.community_summary:
                    context_parts.append(retrieval_result.community_summary)
                for doc in retrieval_result.results[:5]:
                    context_parts.append(doc.text)
                context = "\n---\n".join(context_parts)
                sources = [{"id": r.id, "score": r.score} for r in retrieval_result.results[:5]]

                yield SseEvent(
                    type="qna.status",
                    payload={
                        "phase": "retrieved",
                        "message": f"检索到 {len(sources)} 条相关结果",
                        "sources": sources,
                    },
                ).to_sse_line()
            except Exception:
                yield SseEvent(
                    type="qna.status",
                    payload={
                        "phase": "retrieved",
                        "message": "未找到知识库内容，将直接回答",
                    },
                ).to_sse_line()

            # 阶段 2: LLM 流式生成
            yield SseEvent(
                type="qna.status",
                payload={
                    "phase": "generating",
                    "message": "正在生成回答...",
                },
            ).to_sse_line()

            # 构建提示词
            if context:
                prompt = (
                    "请基于以下上下文回答用户问题。\n\n"
                    f"上下文：\n{context}\n\n"
                    f"用户问题：{query}\n\n"
                    "请给出清晰、准确的回答。"
                )
            else:
                prompt = query

            # 流式调用 LLM
            async for chunk in gateway.stream_complete(
                prompt=prompt,
                task_type="qna.answer",
                workspace_id=workspace_id,
                layer="qna",
                node="stream_answer",
            ):
                yield SseEvent(
                    type="qna.chunk",
                    payload={"content": chunk},
                ).to_sse_line()

            # 完成
            yield SseEvent(
                type="qna.status",
                payload={
                    "phase": "complete",
                    "message": "回答完成",
                },
            ).to_sse_line()

            yield SseEvent.done(task_id="").to_sse_line()

        except Exception as exc:
            yield SseEvent.error(
                message=f"Q&A 处理出错: {exc}",
                code="qna_error",
            ).to_sse_line()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
