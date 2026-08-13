"""SSE 通用工具 — 事件订阅与响应构造（E12 流式基础设施）。

供统一交互入口（interact）与任务事件流（stream_generate）复用，
避免各路由重复实现事件订阅 / 心跳保活 / 断连清理逻辑。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse

from app.streaming import event_bus
from app.streaming.models import SseEvent

KEEPALIVE_INTERVAL = 30  # 心跳间隔（秒）


async def subscribe_task_events(
    channel: str,
    *initial_events: SseEvent,
) -> AsyncGenerator[str, None]:
    """订阅频道并生成 SSE 事件流（自动心跳保活与断连清理）。

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


def sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
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
