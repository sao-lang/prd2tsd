"""SSE 流式生成路由 — 任务事件流 + 流式生成。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_orchestrator
from app.api.schemas.streaming import StreamGenerateRequest
from app.auth.deps import get_current_user
from app.models.user import User
from app.streaming import event_bus
from app.streaming.models import SseEvent
from app.task_manager import task_manager

router = APIRouter(prefix="/api/v1", tags=["streaming"])

KEEPALIVE_INTERVAL = 30  # 心跳间隔（秒）


async def _subscribe_task_events(
    channel: str,
    *initial_events: SseEvent,
) -> AsyncGenerator[str, None]:
    """通用 SSE 事件订阅生成器。

    订阅 channel，自动处理心跳保活和客户端断连清理。
    可选的初始事件先于订阅发送。

    Args:
        channel: 事件频道。
        initial_events: 在订阅前发送的初始事件。

    Yields:
        SSE 格式的事件行。
    """
    # 发送初始事件（在订阅之前，确保客户端看到）
    for event in initial_events:
        yield event.to_sse_line()

    queue = await event_bus.subscribe(channel)
    try:
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=KEEPALIVE_INTERVAL,
                )
                yield event.to_sse_line()
                if event.type in ("done", "error"):
                    break
            except TimeoutError:
                yield SseEvent.keepalive().to_sse_line()
    except asyncio.CancelledError:
        pass
    finally:
        await event_bus.unsubscribe(channel, queue)


def _sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    """创建标准 SSE StreamingResponse。

    Args:
        generator: SSE 事件生成器。

    Returns:
        StreamingResponse 实例。
    """
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
        return _sse_response(
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

    return _sse_response(_subscribe_task_events(channel, snapshot))


@router.post("/generate/stream")
async def create_streaming_generation(
    req: StreamGenerateRequest,
    current_user: User = Depends(get_current_user),
    orchestrator=Depends(get_orchestrator),
) -> StreamingResponse:
    """一键提交 PRD 生成任务 + 全程 SSE 流式推送。

    创建任务后立即返回 SSE 流，实时推送进度、日志和最终结果。

    Args:
        req: 流式生成请求体。
        current_user: 当前用户。
        orchestrator: 主编排器实例。

    Returns:
        StreamingResponse (text/event-stream)。
    """
    # 从 team_memberships 中提取用户角色
    user_role = ""
    if current_user.team_memberships:
        first_membership = current_user.team_memberships[0]
        user_role = (
            getattr(first_membership.role, "name", "")
            if hasattr(first_membership, "role")
            else ""
        )

    task_id = await task_manager.create_task(
        prd_raw=req.prd_content,
        prd_file_type=req.prd_type,
        workspace_id=req.workspace_id,
        user_id=str(current_user.id),
        user_role=user_role,
        orchestrator=orchestrator,
    )

    channel = f"task:{task_id}"

    created_event = SseEvent(
        type="task.created",
        payload={"task_id": task_id, "status": "running"},
    )

    return _sse_response(_subscribe_task_events(channel, created_event))


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

    return _sse_response(_subscribe_task_events(channel, review_event))


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
