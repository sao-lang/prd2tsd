"""SSE 流式推送单元测试。"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.streaming.event_bus import EventBus
from app.streaming.models import EVENT_TYPES, SseEvent


class TestSseEvent:
    """SseEvent 数据模型测试。"""

    def test_create_event(self) -> None:
        """验证基本事件创建。"""
        event = SseEvent(type="task.created", payload={"task_id": "test-1"})
        assert event.type == "task.created"
        assert event.payload["task_id"] == "test-1"
        assert event.timestamp != ""  # 自动填充

    def test_event_auto_timestamp(self) -> None:
        """验证时间戳自动填充。"""
        event = SseEvent(type="task.progress", payload={})
        assert "T" in event.timestamp  # ISO 格式

    def test_preserve_timestamp(self) -> None:
        """验证传入时间戳不被覆盖。"""
        event = SseEvent(type="done", payload={}, timestamp="2026-01-01T00:00:00")
        assert event.timestamp == "2026-01-01T00:00:00"

    def test_to_sse_line_format(self) -> None:
        """验证 SSE 协议格式。"""
        event = SseEvent(type="task.created", payload={"task_id": "test-1"})
        sse_line = event.to_sse_line()
        assert sse_line.startswith("data: ")
        assert sse_line.endswith("\n\n")

        # 解析 JSON 内容
        json_str = sse_line[len("data: "):].strip()
        parsed = json.loads(json_str)
        assert parsed["type"] == "task.created"
        assert parsed["payload"]["task_id"] == "test-1"
        assert "timestamp" in parsed

    def test_keepalive_factory(self) -> None:
        """验证 keepalive 工厂方法。"""
        event = SseEvent.keepalive()
        assert event.type == "keepalive"
        assert event.payload == {}

    def test_error_factory(self) -> None:
        """验证 error 工厂方法。"""
        event = SseEvent.error("出错了", "test_error")
        assert event.type == "error"
        assert event.payload["message"] == "出错了"
        assert event.payload["code"] == "test_error"

    def test_done_factory(self) -> None:
        """验证 done 工厂方法。"""
        event = SseEvent.done("task-1", "方案生成完成")
        assert event.type == "done"
        assert event.payload["task_id"] == "task-1"
        assert event.payload["result_summary"] == "方案生成完成"


class TestEventTypes:
    """EVENT_TYPES 常量测试。"""

    def test_event_types_defined(self) -> None:
        """验证所有事件类型都已定义。"""
        expected_types = [
            "task.created",
            "task.progress",
            "task.log",
            "task.status",
            "task.review_required",
            "task.review_resolved",
            "generation.chunk",
            "generation.section",
            "qna.chunk",
            "qna.status",
            "keepalive",
            "done",
            "error",
        ]
        for t in expected_types:
            assert t in EVENT_TYPES, f"缺少事件类型: {t}"
        assert len(EVENT_TYPES) == len(expected_types)


class TestEventBus:
    """EventBus 内存 Pub/Sub 测试。"""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """创建干净的 EventBus 实例。"""
        return EventBus()

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, event_bus: EventBus) -> None:
        """验证订阅后能收到发布的事件。"""
        channel = "test:channel-1"
        queue = await event_bus.subscribe(channel)

        event = SseEvent(type="test.event", payload={"msg": "hello"})
        await event_bus.publish(channel, event)

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.type == "test.event"
        assert received.payload["msg"] == "hello"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, event_bus: EventBus) -> None:
        """验证多个订阅者都能收到事件。"""
        channel = "test:channel-2"
        q1 = await event_bus.subscribe(channel)
        q2 = await event_bus.subscribe(channel)

        event = SseEvent(type="broadcast", payload={"num": 42})
        await event_bus.publish(channel, event)

        r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert r1.payload["num"] == 42
        assert r2.payload["num"] == 42

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus: EventBus) -> None:
        """验证取消订阅后不再收到事件。"""
        channel = "test:channel-3"
        queue = await event_bus.subscribe(channel)
        await event_bus.unsubscribe(channel, queue)

        event = SseEvent(type="after_unsub", payload={})
        await event_bus.publish(channel, event)

        # 验证队列是空的
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_channel_isolation(self, event_bus: EventBus) -> None:
        """验证不同 channel 之间隔离。"""
        q1 = await event_bus.subscribe("ch:a")
        q2 = await event_bus.subscribe("ch:b")

        await event_bus.publish("ch:a", SseEvent(type="a_only", payload={}))

        r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        assert r1.type == "a_only"

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(q2.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_queue_overflow(self, event_bus: EventBus) -> None:
        """验证队列满时静默丢弃不阻塞。"""
        event_bus._queue_maxsize = 2
        channel = "test:overflow"
        await event_bus.subscribe(channel)

        # 填满队列
        for i in range(3):
            await event_bus.publish(channel, SseEvent(type=f"event-{i}", payload={"i": i}))

        # 不会抛出异常即可

    @pytest.mark.asyncio
    async def test_channel_count(self, event_bus: EventBus) -> None:
        """验证活跃频道数统计。"""
        assert event_bus.channel_count == 0
        await event_bus.subscribe("ch:1")
        await event_bus.subscribe("ch:2")
        assert event_bus.channel_count == 2

    @pytest.mark.asyncio
    async def test_subscriber_count(self, event_bus: EventBus) -> None:
        """验证订阅者数统计。"""
        assert event_bus.subscriber_count == 0
        await event_bus.subscribe("ch:1")
        await event_bus.subscribe("ch:1")
        await event_bus.subscribe("ch:2")
        assert event_bus.subscriber_count == 3

    @pytest.mark.asyncio
    async def test_cleanup_empty_channel(self, event_bus: EventBus) -> None:
        """验证取消订阅后空 channel 被清理。"""
        channel = "test:cleanup"
        queue = await event_bus.subscribe(channel)
        assert channel in event_bus._channels

        await event_bus.unsubscribe(channel, queue)
        assert channel not in event_bus._channels
