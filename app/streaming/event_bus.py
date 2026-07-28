"""EventBus — 基于 asyncio.Queue 的内存 Pub/Sub 事件总线。"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logger import get_logger
from app.streaming.models import SseEvent

logger = get_logger("prd2tsd.streaming")


class EventBus:
    """内存事件总线 — 基于 asyncio.Queue 的 Pub/Sub。

    支持多个订阅者监听同一 channel，每个订阅者独立消费。
    当队列满（maxsize=128）时，新消息静默丢弃，避免阻塞 Publisher。
    """

    def __init__(self) -> None:
        """初始化 EventBus。"""
        self._channels: dict[str, set[asyncio.Queue[Any]]] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = 128

    async def publish(self, channel: str, event: SseEvent) -> None:
        """向指定 channel 发布事件。

        所有订阅了该 channel 的队列都将收到事件。
        如果某个订阅者队列已满，该事件对该订阅者静默丢弃。

        Args:
            channel: 频道名称，如 "task:{task_id}"。
            event: 要发布的事件。
        """
        async with self._lock:
            queues = list(self._channels.get(channel, set()))

        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("订阅者队列已满，丢弃事件: channel=%s, event_type=%s", channel, event.type)
            except Exception:
                logger.exception("发布事件异常: channel=%s", channel)

    async def subscribe(self, channel: str) -> asyncio.Queue[Any]:
        """订阅指定 channel。

        Args:
            channel: 频道名称。

        Returns:
            asyncio.Queue，用于消费事件。
        """
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._queue_maxsize)
        async with self._lock:
            if channel not in self._channels:
                self._channels[channel] = set()
            self._channels[channel].add(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue[Any]) -> None:
        """取消订阅。

        从 channel 的订阅者集合中移除指定队列。

        Args:
            channel: 频道名称。
            queue: 要移除的队列。
        """
        async with self._lock:
            if channel in self._channels:
                self._channels[channel].discard(queue)
                # 清理空 channel
                if not self._channels[channel]:
                    del self._channels[channel]

    @property
    def channel_count(self) -> int:
        """当前活跃频道数。"""
        return len(self._channels)

    @property
    def subscriber_count(self) -> int:
        """当前总订阅者数。"""
        return sum(len(qs) for qs in self._channels.values())


# 全局单例
event_bus = EventBus()
