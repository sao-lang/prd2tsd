"""SSE 流式任务路由 — 任务事件流订阅 + 流式审核恢复。

通用 SSE 订阅/响应构造已抽取到 app.streaming.sse 复用。
POST /api/v1/generate/stream 已由 /api/v1/interact?stream=true 替代（Block E B1）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth.deps import get_current_user
from app.models.user import User
from app.streaming.models import SseEvent
from app.streaming.sse import sse_response, subscribe_task_events
from app.task_manager import task_manager

router = APIRouter(prefix="/api/v1", tags=["streaming"])


@router.get("/tasks/{task_id}/events")
async def stream_task_events(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """订阅任务事件流（SSE）。

    通过 SSE 实时推送任务进度、日志、审核请求和完成事件。
    客户端断连时自动清理订阅。

    Args:
        task_id: 任务 ID。
        current_user: 当前用户。

    Returns:
        StreamingResponse (text/event-stream)。
    """
    channel = f"task:{task_id}"

    # 检查任务是否存在
    task = await task_manager.get_task(task_id)
    if task is None:
        return sse_response(
            _single_error_generator("任务不存在", "not_found"),
        )

    # 构建初始快照
    snapshot = SseEvent(
        type="task.snapshot",
        payload={
            "task_id": task_id,
            "status": task.status,
            "progress": task.progress,
            "stage": task.stage or "",
        },
    )

    return sse_response(subscribe_task_events(channel, snapshot))


@router.post("/tasks/{task_id}/stream-review")
async def stream_review_task(
    task_id: str,
    decision: str = "approved",
    comment: str = "",
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """审核任务 + 流式恢复执行（SSE）。

    处理人工审核结果，恢复被 interrupt 暂停的图执行，
    并通过 SSE 实时推送后续进度。

    Args:
        task_id: 任务 ID。
        decision: 审核决策 (approved / needs_changes)。
        comment: 审核意见。
        current_user: 当前用户。

    Returns:
        StreamingResponse (text/event-stream)。
    """
    if decision not in ("approved", "needs_changes"):
        raise HTTPException(status_code=400, detail="决策必须为 approved 或 needs_changes")

    # 检查任务状态
    task = await task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "paused":
        raise HTTPException(status_code=400, detail=f"任务状态不是 paused (当前: {task.status})")

    # 处理审核
    stage = task.interrupt_stage or ""
    success = await task_manager.resolve_review(task_id, stage, decision, comment)
    if not success:
        raise HTTPException(status_code=500, detail="审核处理失败")

    channel = f"task:{task_id}"

    review_event = SseEvent(
        type="task.review_resolved",
        payload={
            "task_id": task_id,
            "stage": stage,
            "decision": decision,
        },
    )

    return sse_response(subscribe_task_events(channel, review_event))


async def _single_error_generator(
    message: str,
    code: str = "internal_error",
) -> AsyncGenerator[str, None]:
    """生成单条错误 SSE 事件。

    Args:
        message: 错误描述。
        code: 错误码。

    Yields:
        SSE 格式的错误事件行。
    """
    yield SseEvent.error(message=message, code=code).to_sse_line()
