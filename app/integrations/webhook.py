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
        self._webhooks: dict[str, dict[str, str]] = {}  # {workspace_id: {event: url}}

    def register_webhook(
        self,
        workspace_id: str,
        url: str,
        event: str = "task.completed",
    ) -> None:
        """注册 Webhook。

        Args:
            workspace_id: 工作空间 ID。
            url: 回调 URL。
            event: 事件类型。
        """
        if workspace_id not in self._webhooks:
            self._webhooks[workspace_id] = {}
        self._webhooks[workspace_id][event] = url
        logger.info(
            "Webhook 已注册: workspace=%s, event=%s, url=%s",
            workspace_id, event, url,
        )

    def unregister_webhook(self, workspace_id: str, event: str) -> bool:
        """注销 Webhook。

        Args:
            workspace_id: 工作空间 ID。
            event: 事件类型。

        Returns:
            是否注销成功。
        """
        if workspace_id in self._webhooks and event in self._webhooks[workspace_id]:
            del self._webhooks[workspace_id][event]
            return True
        return False

    def get_webhook_url(self, workspace_id: str, event: str) -> str | None:
        """获取 Webhook URL。

        Args:
            workspace_id: 工作空间 ID。
            event: 事件类型。

        Returns:
            Webhook URL，未注册时返回 None。
        """
        return self._webhooks.get(workspace_id, {}).get(event)

    def list_webhooks(self, workspace_id: str) -> list[dict[str, str]]:
        """列出工作空间的所有 Webhook。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            Webhook 列表，每项包含 event 和 url。
        """
        hooks = self._webhooks.get(workspace_id, {})
        return [{"event": event, "url": url} for event, url in hooks.items()]

    async def notify(
        self,
        event: str,
        payload: dict[str, Any],
        sender: WebhookSender | None = None,
    ) -> list[dict[str, Any]]:
        """通知所有注册了该事件的 Webhook。

        Args:
            event: 事件类型。
            payload: 负载数据。
            sender: Webhook 发送器。

        Returns:
            各 Webhook 的发送结果。
        """
        s = sender or WebhookSender()
        results: list[dict[str, Any]] = []
        for ws_id, hooks in self._webhooks.items():
            url = hooks.get(event)
            if url:
                result = await s.send(url, event, {
                    "workspace_id": ws_id,
                    **payload,
                })
                results.append(result)
        return results


# 全局单例
integration_hub = IntegrationHub()
