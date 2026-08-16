"""Webhook 发送器 — 方案完成时回调指定 URL。"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.logger import get_logger

logger = get_logger("prd2tsd.webhook")


class WebhookSender:
    """Webhook 发送器。

    支持 HMAC-SHA256 签名验证。
    """

    def __init__(self, secret: str = "") -> None:
        """初始化 Webhook 发送器。

        Args:
            secret: 签名密钥（为空时不签名）。
        """
        self.secret = secret

    async def send(
        self,
        url: str,
        event: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """发送 Webhook 通知。

        Args:
            url: 回调 URL。
            event: 事件类型（如 task.completed）。
            payload: 负载数据。

        Returns:
            发送结果。{"success": bool, "status_code": int, "error": str}
        """
        body = {
            "event": event,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": payload,
        }
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "Prd2Tsd-Webhook/1.0",
        }

        # HMAC-SHA256 签名
        if self.secret:
            signature = hmac.new(
                self.secret.encode("utf-8"),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = signature

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, content=body_bytes, headers=headers)

            logger.info(
                "Webhook 已发送: %s | event=%s | status=%d",
                url, event, resp.status_code,
            )
            return {
                "success": 200 <= resp.status_code < 300,
                "status_code": resp.status_code,
                "error": None,
            }

        except httpx.TimeoutException:
            logger.warning("Webhook 超时: %s", url)
            return {"success": False, "status_code": 0, "error": "timeout"}
        except Exception as exc:
            logger.warning("Webhook 发送失败: %s - %s", url, exc)
            return {"success": False, "status_code": 0, "error": str(exc)}

    async def send_task_completed(
        self,
        url: str,
        task_id: str,
        workspace_id: str,
        summary: str = "",
    ) -> dict[str, Any]:
        """发送任务完成通知。

        Args:
            url: 回调 URL。
            task_id: 任务 ID。
            workspace_id: 工作空间 ID。
            summary: 任务摘要。

        Returns:
            发送结果。
        """
        return await self.send(
            url=url,
            event="task.completed",
            payload={
                "task_id": task_id,
                "workspace_id": workspace_id,
                "summary": summary,
                "status": "completed",
            },
        )


class IntegrationHub:
    """集成中心 — 管理所有 Webhook 配置和发送。"""

    def __init__(self) -> None:
        """初始化集成中心。"""
        # 内存缓存（写穿持久化到 webhook_subscriptions 表）
        self._webhooks: dict[str, dict[str, str]] = {}  # {workspace_id: {event: url}}

    async def register_webhook(
        self,
        workspace_id: str,
        url: str,
        event: str = "task.completed",
        secret: str = "",
        db: Any | None = None,
    ) -> None:
        """注册 Webhook。

        Args:
            workspace_id: 工作空间 ID。
            url: 回调 URL。
            event: 事件类型。
            secret: 签名密钥（可选）。
            db: 数据库会话（可选，未提供时自建）。
        """
        if workspace_id not in self._webhooks:
            self._webhooks[workspace_id] = {}
        self._webhooks[workspace_id][event] = url
        await self._persist_upsert(workspace_id, event, url, secret, db)
        logger.info(
            "Webhook 已注册: workspace=%s, event=%s, url=%s",
            workspace_id, event, url,
        )

    async def unregister_webhook(
        self,
        workspace_id: str,
        event: str,
        db: Any | None = None,
    ) -> bool:
        """注销 Webhook。

        Args:
            workspace_id: 工作空间 ID。
            event: 事件类型。
            db: 数据库会话（可选）。

        Returns:
            是否注销成功。
        """
        if workspace_id in self._webhooks and event in self._webhooks[workspace_id]:
            del self._webhooks[workspace_id][event]
            await self._persist_delete(workspace_id, event, db)
            return True
        return False

    async def get_webhook_url(
        self,
        workspace_id: str,
        event: str,
        db: Any | None = None,
    ) -> str | None:
        """获取 Webhook URL。

        Args:
            workspace_id: 工作空间 ID。
            event: 事件类型。
            db: 数据库会话（可选）。

        Returns:
            Webhook URL，未注册时返回 None。
        """
        url = self._webhooks.get(workspace_id, {}).get(event)
        if url is not None:
            return url
        return await self._load_url(workspace_id, event, db)

    async def list_webhooks(
        self,
        workspace_id: str,
        db: Any | None = None,
    ) -> list[dict[str, str]]:
        """列出工作空间的所有 Webhook。

        Args:
            workspace_id: 工作空间 ID。
            db: 数据库会话（可选）。

        Returns:
            Webhook 列表，每项包含 event 和 url。
        """
        hooks = dict(self._webhooks.get(workspace_id, {}))
        try:
            from sqlalchemy import select

            from app.models.persistence import WebhookSubscription

            async with self._session(db) as session:
                result = await session.execute(
                    select(WebhookSubscription).where(
                        WebhookSubscription.workspace_id == workspace_id
                    )
                )
                for row in result.scalars().all():
                    hooks.setdefault(row.event, row.url)
        except Exception as exc:
            logger.warning("读取 Webhook 持久化失败: %s", exc)
        return [{"event": event, "url": url} for event, url in hooks.items()]

    async def notify(
        self,
        event: str,
        payload: dict[str, Any],
        sender: WebhookSender | None = None,
        db: Any | None = None,
    ) -> list[dict[str, Any]]:
        """通知所有注册了该事件的 Webhook。

        Args:
            event: 事件类型。
            payload: 负载数据。
            sender: Webhook 发送器。
            db: 数据库会话（可选）。

        Returns:
            各 Webhook 的发送结果。
        """
        s = sender or WebhookSender()
        results: list[dict[str, Any]] = []
        targets: list[tuple[str, str, str]] = []  # (ws_id, url, secret)
        for ws_id, hooks in self._webhooks.items():
            if event in hooks:
                targets.append((ws_id, hooks[event], ""))
        try:
            from sqlalchemy import select

            from app.models.persistence import WebhookSubscription

            async with self._session(db) as session:
                result = await session.execute(
                    select(WebhookSubscription).where(
                        WebhookSubscription.event == event
                    )
                )
                for row in result.scalars().all():
                    targets.append((row.workspace_id, row.url, row.secret or ""))
        except Exception as exc:
            logger.warning("读取 Webhook 订阅失败: %s", exc)

        seen: set[tuple[str, str]] = set()
        for ws_id, url, _secret in targets:
            key = (ws_id, url)
            if key in seen:
                continue
            seen.add(key)
            result = await s.send(url, event, {
                "workspace_id": ws_id,
                **payload,
            })
            results.append(result)
        return results

    def _session(self, db: Any | None) -> Any:
        """返回数据库会话上下文管理器（自建或复用）。"""
        if db is not None:
            class _Ctx:
                def __init__(self, s: Any) -> None:
                    self.s = s

                async def __aenter__(self) -> Any:
                    return self.s

                async def __aexit__(self, *args: Any) -> None:
                    return None

            return _Ctx(db)
        from app.core.connections import connection_manager

        return connection_manager.get("postgres").get_session()

    async def _persist_upsert(
        self,
        workspace_id: str,
        event: str,
        url: str,
        secret: str,
        db: Any | None,
    ) -> None:
        """写穿：注册记录到 webhook_subscriptions 表。"""
        try:
            from datetime import UTC, datetime

            from app.models.persistence import WebhookSubscription

            async with self._session(db) as session:
                from sqlalchemy.dialects.postgresql import insert

                stmt = insert(WebhookSubscription).values(
                    workspace_id=workspace_id,
                    event=event,
                    url=url,
                    secret=secret,
                    created_at=datetime.now(UTC),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[WebhookSubscription.workspace_id, WebhookSubscription.event],
                    set_={"url": url, "secret": secret},
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            logger.warning("Webhook 持久化注册失败: %s", exc)

    async def _persist_delete(self, workspace_id: str, event: str, db: Any | None) -> None:
        """写穿：删除 webhook_subscriptions 记录。"""
        try:
            from sqlalchemy import delete

            from app.models.persistence import WebhookSubscription

            async with self._session(db) as session:
                await session.execute(
                    delete(WebhookSubscription).where(
                        WebhookSubscription.workspace_id == workspace_id,
                        WebhookSubscription.event == event,
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Webhook 持久化注销失败: %s", exc)

    async def _load_url(self, workspace_id: str, event: str, db: Any | None) -> str | None:
        """从持久化存储读取单个 Webhook URL。"""
        try:
            from sqlalchemy import select

            from app.models.persistence import WebhookSubscription

            async with self._session(db) as session:
                result = await session.execute(
                    select(WebhookSubscription.url).where(
                        WebhookSubscription.workspace_id == workspace_id,
                        WebhookSubscription.event == event,
                    )
                )
                return result.scalar_one_or_none()  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("读取 Webhook URL 失败: %s", exc)
            return None


# 全局单例
integration_hub = IntegrationHub()
