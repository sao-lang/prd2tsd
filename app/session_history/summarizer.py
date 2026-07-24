"""会话摘要生成器 — LLM 自动生成会话标题和摘要。"""

from __future__ import annotations

from app.core.logger import get_logger

logger = get_logger("prd2tsd.session_summarizer")


class SessionSummarizer:
    """会话摘要生成器。

    使用 LLM 自动生成会话标题和内容摘要。
    当前为占位实现，返回基于内容的简单截取。
    """

    async def generate_title(self, first_message: str) -> str:
        """根据首条消息生成会话标题。

        Args:
            first_message: 用户的首条消息。

        Returns:
            生成的标题。
        """
        content = first_message.strip()
        if not content:
            return "新会话"

        # 截取前 50 个字符作为标题
        title = content[:50]
        if len(content) > 50:
            title += "..."
        return title

    async def generate_summary(self, messages: list[dict]) -> str:
        """根据消息内容生成会话摘要。

        Args:
            messages: 消息列表，每项包含 role 和 content。

        Returns:
            生成的摘要文本。
        """
        if not messages:
            return ""

        # 简单摘取用户问题和助手回复的前几句
        user_msgs = [m["content"][:100] for m in messages if m.get("role") == "user"]
        assistant_msgs = [m["content"][:100] for m in messages if m.get("role") == "assistant"]

        parts: list[str] = []
        if user_msgs:
            parts.append(f"用户咨询: {'; '.join(user_msgs[:3])}")
        if assistant_msgs:
            parts.append(f"助手回复: {'; '.join(assistant_msgs[:3])}")

        return "; ".join(parts) if parts else "会话摘要"
