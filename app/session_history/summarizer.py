"""会话摘要生成器 — LLM 自动生成会话标题和摘要。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.llm_gateway import gateway as _default_gateway

logger = get_logger("prd2tsd.session_summarizer")


class SessionSummarizer:
    """会话摘要生成器。

    使用 LLM 自动生成会话标题和内容摘要。
    """

    def __init__(self, llm_gateway: Any = None) -> None:
        """初始化会话摘要生成器。

        Args:
            llm_gateway: LLM Gateway 实例（可选，用于测试注入）。
                         为 None 时使用模块级单例。
        """
        self._gateway = llm_gateway or _default_gateway

    async def generate_title(self, first_message: str) -> str:
        """根据首条消息生成会话标题。

        Args:
            first_message: 用户的首条消息。

        Returns:
            生成的标题（失败时返回默认值）。
        """
        content = first_message.strip()
        if not content:
            return "新会话"

        try:
            resp = await self._gateway.complete(
                prompt=f"为以下对话生成一个简短的标题（10 字以内）：\n\n{content[:200]}",
                task_type="session_title",
                max_tokens=20,
                temperature=0.3,
            )
            title = resp.content.strip().strip('"').strip("'")
            return title[:50] if title else content[:50]
        except Exception:
            # 降级：截取前 50 个字符
            title = content[:50]
            if len(content) > 50:
                title += "..."
            return title

    async def generate_summary(self, messages: list[dict[str, Any]]) -> str:
        """根据消息内容生成会话摘要。

        Args:
            messages: 消息列表，每项包含 role 和 content。

        Returns:
            生成的摘要文本。
        """
        if not messages:
            return ""

        try:
            # 提取最近的消息用于摘要
            recent = messages[-10:]
            conversation = "\n".join(
                f"{m.get('role', '')}: {m.get('content', '')[:200]}"
                for m in recent
            )
            resp = await self._gateway.complete(
                prompt=f"总结以下对话的核心内容（50 字以内）：\n\n{conversation}",
                task_type="session_summary",
                max_tokens=100,
                temperature=0.3,
            )
            summary = resp.content.strip()
            if summary:
                return summary
        except Exception:
            logger.warning("LLM 摘要生成失败，降级到简单摘取")

        # 降级：简单摘取
        user_msgs = [m["content"][:100] for m in messages if m.get("role") == "user"]
        assistant_msgs = [m["content"][:100] for m in messages if m.get("role") == "assistant"]

        parts: list[str] = []
        if user_msgs:
            parts.append(f"用户咨询: {'; '.join(user_msgs[:3])}")
        if assistant_msgs:
            parts.append(f"助手回复: {'; '.join(assistant_msgs[:3])}")

        return "; ".join(parts) if parts else "会话摘要"
