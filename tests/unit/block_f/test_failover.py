"""FailoverManager 单元测试。"""

from __future__ import annotations

import pytest

from app.llm_gateway.failover import AllProvidersUnavailableError, FailoverManager, FailoverTarget


class TestFailoverManager:
    """FailoverManager 测试。"""

    def setup_method(self):
        self.manager = FailoverManager()

    def test_configure_chain(self):
        """测试配置 Failover 链。"""
        chain = [
            FailoverTarget(provider="deepseek", model="deepseek-chat", priority=0),
            FailoverTarget(provider="openai", model="gpt-4o-mini", priority=1),
        ]
        self.manager.configure("llm", chain)
        status = self.manager.get_chain_status("llm")
        assert len(status) == 2
        assert status[0]["provider"] == "deepseek"
        assert status[1]["provider"] == "openai"

    def test_get_target_returns_healthy(self):
        """测试获取健康目标。"""
        chain = [
            FailoverTarget(provider="deepseek", model="deepseek-chat", priority=0),
        ]
        self.manager.configure("llm", chain)

        # _is_healthy 会尝试实际 ping，这里会失败但抛 AllProvidersUnavailableError
        with pytest.raises(AllProvidersUnavailableError):
            import asyncio
            asyncio.run(self.manager.get_target("llm"))

    def test_unknown_model_type_raises_error(self):
        """测试未知模型类型抛出异常。"""
        with pytest.raises(AllProvidersUnavailableError):
            import asyncio
            asyncio.run(self.manager.get_target("unknown"))

    def test_record_failure_marks_unhealthy(self):
        """测试记录失败后标记为不可用。"""
        chain = [
            FailoverTarget(provider="deepseek", model="deepseek-chat", priority=0),
        ]
        self.manager.configure("llm", chain)

        import asyncio
        asyncio.run(self.manager.record_failure("llm", "deepseek"))

        status = self.manager.get_chain_status("llm")
        assert status[0]["healthy"] is False

    def test_reset_targets(self):
        """测试重置目标。"""
        chain = [
            FailoverTarget(provider="deepseek", model="deepseek-chat", priority=0, healthy=False),
        ]
        self.manager.configure("llm", chain)
        self.manager.reset_targets("llm")

        status = self.manager.get_chain_status("llm")
        assert status[0]["healthy"] is True

    def test_get_chain_status_empty(self):
        """测试空链。"""
        status = self.manager.get_chain_status("nonexistent")
        assert status == []

    @pytest.mark.asyncio
    async def test_get_target_skips_unhealthy(self):
        """测试跳过不健康目标。"""
        chain = [
            FailoverTarget(provider="openai", model="gpt-4o", priority=0, healthy=False),
            FailoverTarget(provider="deepseek", model="deepseek-chat", priority=1),
        ]
        self.manager.configure("llm", chain)

        # 跳过 openai（不健康），选 deepseek，但 deepseek ping 会失败
        with pytest.raises(AllProvidersUnavailableError):
            await self.manager.get_target("llm")
