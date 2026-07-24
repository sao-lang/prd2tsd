"""块 E — 集成生态集成测试（E5：Webhook 注册/通知/Orchestrator 联动）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.webhook import IntegrationHub, WebhookSender
from app.orchestrator.main_graph import FinalAssemblyNode
from app.orchestrator.state import make_initial_state


class TestWebhookSender:
    """Webhook 发送器集成测试。"""

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        """验证 Webhook 成功发送。"""
        sender = WebhookSender(secret="test-secret")

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            result = await sender.send(
                url="https://example.com/hook",
                event="task.completed",
                payload={"task_id": "task-1"},
            )

        assert result["success"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_send_failure_returns_error(self) -> None:
        """验证 Webhook 发送失败返回错误信息。"""
        sender = WebhookSender()

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = Exception("Connection refused")

            result = await sender.send(
                url="https://example.com/hook",
                event="task.completed",
                payload={},
            )

        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_send_timeout(self) -> None:
        """验证 Webhook 超时处理。"""
        import httpx
        sender = WebhookSender()

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timeout")

            result = await sender.send(
                url="https://example.com/hook",
                event="task.completed",
                payload={},
            )

        assert result["success"] is False
        assert result["status_code"] == 0
        assert result["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_send_task_completed(self) -> None:
        """验证发送任务完成通知。"""
        sender = WebhookSender()

        send_result = {"success": True, "status_code": 200, "error": None}
        with patch.object(sender, "send", new=AsyncMock(return_value=send_result)):
            result = await sender.send_task_completed(
                url="https://example.com/hook",
                task_id="task-1",
                workspace_id="ws-1",
                summary="Test task",
            )

        assert result["success"] is True


class TestIntegrationHub:
    """IntegrationHub 集成测试。"""

    def test_register_and_list(self) -> None:
        """验证 Webhook 注册和列表。"""
        hub = IntegrationHub()
        hub.register_webhook("ws-1", "https://example.com/hook1", "task.completed")
        hub.register_webhook("ws-1", "https://example.com/hook2", "task.started")

        hooks = hub.list_webhooks("ws-1")
        assert len(hooks) == 2
        assert any(h["event"] == "task.completed" for h in hooks)
        assert any(h["event"] == "task.started" for h in hooks)

    def test_list_empty_workspace(self) -> None:
        """验证未注册的工作空间返回空列表。"""
        hub = IntegrationHub()
        assert hub.list_webhooks("ws-nonexistent") == []

    def test_unregister_success(self) -> None:
        """验证注销已注册的 Webhook。"""
        hub = IntegrationHub()
        hub.register_webhook("ws-1", "https://example.com/hook", "task.completed")
        assert hub.unregister_webhook("ws-1", "task.completed") is True
        assert hub.get_webhook_url("ws-1", "task.completed") is None

    def test_unregister_nonexistent(self) -> None:
        """验证注销不存在的 Webhook 返回 False。"""
        hub = IntegrationHub()
        assert hub.unregister_webhook("ws-x", "task.completed") is False

    @pytest.mark.asyncio
    async def test_notify_triggers_all_matching_webhooks(self) -> None:
        """验证 notify 触发所有匹配的 Webhook。"""
        hub = IntegrationHub()
        hub.register_webhook("ws-1", "https://example.com/hook1", "task.completed")
        hub.register_webhook("ws-2", "https://example.com/hook2", "task.completed")
        # 不同事件类型不应触发
        hub.register_webhook("ws-1", "https://example.com/hook3", "task.started")

        mock_sender = MagicMock()
        mock_sender.send = AsyncMock(return_value={"success": True, "status_code": 200, "error": None})

        results = await hub.notify(
            event="task.completed",
            payload={"task_id": "task-1"},
            sender=mock_sender,
        )

        # 只有 2 个注册了 task.completed 的 Webhook 被触发
        assert len(results) == 2


class TestFinalAssemblyNodeWebhook:
    """FinalAssemblyNode Webhook 联动测试。"""

    @pytest.mark.asyncio
    async def test_final_assembly_triggers_webhook(self) -> None:
        """验证 FinalAssemblyNode 完成后触发 Webhook 通知。"""
        node = FinalAssemblyNode()
        state = make_initial_state(
            task_id="test-task",
            prd_raw="# Test",
            workspace_id="ws-1",
            user_id="user-1",
        )

        with patch("app.integrations.webhook.integration_hub.notify", new=AsyncMock()) as mock_notify:
            result = await node.run(state)

        assert result["status"] == "complete"
        assert result["progress"] == 1.0
        mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_final_assembly_webhook_failure_does_not_block(self) -> None:
        """验证 Webhook 失败不影响主流程。"""
        node = FinalAssemblyNode()
        state = make_initial_state(
            task_id="test-task",
            prd_raw="# Test",
            workspace_id="ws-1",
            user_id="user-1",
        )

        with patch("app.integrations.webhook.integration_hub.notify", side_effect=Exception("Webhook failed")):
            result = await node.run(state)

        # 主流程仍然完成
        assert result["status"] == "complete"
        assert result["progress"] == 1.0
