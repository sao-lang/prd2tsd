"""会话导出 — Markdown / JSON 格式。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block_e import Session, SessionMessage


class SessionExporter:
    """会话导出服务。

    支持 Markdown 和 JSON 两种导出格式。
    """

    async def export(
        self,
        db: AsyncSession,
        session_id: str,
        fmt: str = "markdown",
    ) -> str:
        """导出会话。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。
            fmt: 导出格式（markdown / json）。

        Returns:
            导出内容。

        Raises:
            ValueError: 不支持的格式或会话不存在。
        """
        # 获取会话
        result = await db.execute(
            select(Session).where(Session.id == session_id, Session.deleted_at.is_(None)),
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError(f"会话不存在: {session_id}")

        # 获取消息
        result = await db.execute(
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.turn_index.asc()),
        )
        messages = result.scalars().all()

        if fmt == "markdown":
            return self._to_markdown(session, messages)
        if fmt == "json":
            return self._to_json(session, messages)
        raise ValueError(f"不支持的导出格式: {fmt}")

    def _to_markdown(
        self,
        session: Session,
        messages: list[SessionMessage],
    ) -> str:
        """导出为 Markdown。

        Args:
            session: 会话 ORM 对象。
            messages: 消息列表。

        Returns:
            Markdown 格式的导出内容。
        """
        lines: list[str] = []
        lines.append(f"# {session.title}")
        lines.append("")
        lines.append(f"> 会话类型: {session.session_type}")
        lines.append(f"> 状态: {session.status}")
        lines.append(f"> 消息数: {session.message_count}")
        if session.summary:
            lines.append("")
            lines.append("## 摘要")
            lines.append("")
            lines.append(session.summary)
        lines.append("")
        lines.append("---")
        lines.append("")

        for msg in messages:
            role_label = {
                "user": "👤 **用户**",
                "assistant": "🤖 **助手**",
                "system": "⚙️ **系统**",
                "tool": "🔧 **工具**",
            }.get(msg.role, f"**{msg.role}**")

            lines.append(f"### {role_label}（第 {msg.turn_index + 1} 轮）")
            lines.append("")
            lines.append(msg.content)
            lines.append("")

        return "\n".join(lines)

    def _to_json(
        self,
        session: Session,
        messages: list[SessionMessage],
    ) -> str:
        """导出为 JSON。

        Args:
            session: 会话 ORM 对象。
            messages: 消息列表。

        Returns:
            JSON 格式的导出内容。
        """
        data = {
            "session": {
                "id": str(session.id),
                "title": session.title,
                "session_type": session.session_type,
                "status": session.status,
                "message_count": session.message_count,
                "summary": session.summary,
                "created_at": session.created_at.isoformat() if session.created_at else None,
            },
            "messages": [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "content_type": m.content_type,
                    "turn_index": m.turn_index,
                    "token_count": m.token_count,
                    "model_used": m.model_used,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
            "exported_at": datetime.now(UTC).isoformat(),
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
