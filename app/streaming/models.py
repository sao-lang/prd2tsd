"""SSE 事件数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SseEvent:
    """SSE 事件。

    Attributes:
        type: 事件类型。
        payload: 事件数据。
        timestamp: ISO 格式时间戳。
    """

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        """自动填充时间戳（如果未提供）。"""
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def to_sse_line(self) -> str:
        """将事件序列化为 SSE 协议格式。

        Returns:
            SSE 格式字符串，以 "data: " 开头，双换行结尾。
        """
        import json
        data = json.dumps({
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }, ensure_ascii=False)
        return f"data: {data}\n\n"

    @classmethod
    def keepalive(cls) -> SseEvent:
        """创建保活心跳事件。"""
        return cls(type="keepalive", payload={})

    @classmethod
    def error(cls, message: str, code: str = "internal_error") -> SseEvent:
        """创建错误事件。

        Args:
            message: 错误描述。
            code: 错误码。

        Returns:
            SseEvent 实例。
        """
        return cls(type="error", payload={"message": message, "code": code})

    @classmethod
    def done(cls, task_id: str, result_summary: str = "") -> SseEvent:
        """创建任务完成事件。

        Args:
            task_id: 任务 ID。
            result_summary: 结果摘要。

        Returns:
            SseEvent 实例。
        """
        return cls(type="done", payload={"task_id": task_id, "result_summary": result_summary})


# 事件类型一览
EVENT_TYPES: dict[str, str] = {
    "task.created": "任务创建成功",
    "task.progress": "进度更新 (0.0~1.0) + 当前阶段",
    "task.log": "日志消息",
    "task.status": "状态变更 (running/paused/complete/failed)",
    "task.review_required": "需要人工审核 — 推送审核上下文",
    "task.review_resolved": "审核已处理",
    "task.saved": "任务结果已保存（SaveSessionNode）",
    "task.snapshot": "任务初始快照（SSE 订阅）",
    "chat.status": "对话阶段状态 (generating)",
    "chat.chunk": "对话流式片段",
    "chat.done": "对话完成",
    "chat.clarify": "需要澄清（输入不明确）",
    "generation.chunk": "流式文档片段 — 逐 chunk 推送",
    "generation.section": "Section 级别状态 (generating/done)",
    "qna.chunk": "流式 Q&A 回答片段",
    "qna.status": "Q&A 阶段状态 (retrieving/generating)",
    "qna.done": "Q&A 回答完成",
    "keepalive": "30s 心跳保活",
    "done": "任务完成",
    "error": "错误事件",
}
