"""Prompt 版本管理单元测试。"""

from __future__ import annotations

import pytest

from app.core.prompt_registry.models import PromptVersion, ABTestConfig
from app.core.prompt_registry.registry import PromptRegistry
from app.core.prompt_registry.storage import DuplicateHashError


class TestPromptVersionModel:
    """PromptVersion 模型单元测试。"""

    def test_create_version(self) -> None:
        """验证创建版本。"""
        pv = PromptVersion(
            name="analysis.requirement",
            version=1,
            content="你是一个需求分析专家",
        )
        assert pv.name == "analysis.requirement"
        assert pv.version == 1
        assert pv.is_active is False

    def test_version_with_tags(self) -> None:
        """验证带标签的版本。"""
        pv = PromptVersion(
            name="test.prompt",
            version=2,
            content="test",
            tags=["stable", "production"],
        )
        assert "stable" in pv.tags

    def test_ab_test_config_defaults(self) -> None:
        """验证 A/B 测试默认值。"""
        config = ABTestConfig(
            prompt_name="test.prompt",
            version_a=1,
            version_b=2,
        )
        assert config.traffic_split == 0.5
        assert config.metric == "eval_score"
        assert config.is_active is False


class TestPromptRegistry:
    """Prompt 注册器单元测试。"""

    @pytest.fixture
    def registry(self) -> PromptRegistry:
        return PromptRegistry()

    @pytest.mark.asyncio
    async def test_register_first_version(self, registry: PromptRegistry) -> None:
        """验证首次注册为 v1。"""
        pv = await registry.register(
            name="test.prompt",
            content="你是一个助手",
            author="test",
            changelog="初始版本",
        )
        assert pv.version == 1
        assert pv.is_active is True
        assert pv.name == "test.prompt"

    @pytest.mark.asyncio
    async def test_register_auto_increment(self, registry: PromptRegistry) -> None:
        """验证版本号自动递增。"""
        await registry.register("t", "v1")
        pv2 = await registry.register("t", "v2")
        assert pv2.version == 2

    @pytest.mark.asyncio
    async def test_duplicate_content_raises_error(self, registry: PromptRegistry) -> None:
        """验证相同内容重复注册抛出异常。"""
        await registry.register("t", "相同内容")
        with pytest.raises(DuplicateHashError):
            await registry.register("t", "相同内容")

    @pytest.mark.asyncio
    async def test_get_active_returns_latest(self, registry: PromptRegistry) -> None:
        """验证获取激活版本返回最新。"""
        await registry.register("t", "v1")
        pv2 = await registry.register("t", "v2")
        active = await registry.get_active("t")
        assert active.version == pv2.version
        assert active.content == "v2"

    @pytest.mark.asyncio
    async def test_get_active_not_found_raises_error(self, registry: PromptRegistry) -> None:
        """验证获取不存在的 Prompt 抛出异常。"""
        with pytest.raises(Exception):
            await registry.get_active("not-exist")

    @pytest.mark.asyncio
    async def test_rollback(self, registry: PromptRegistry) -> None:
        """验证回滚到指定版本。"""
        await registry.register("t", "v1")
        v2 = await registry.register("t", "v2")
        v3 = await registry.register("t", "v3")
        # 回滚到 v1
        rolled = await registry.rollback("t", 1)
        assert rolled.version > v3.version  # 新版本号
        assert rolled.content == "v1"
        # 验证当前激活的是回滚后的版本
        active = await registry.get_active("t")
        assert active.content == "v1"

    @pytest.mark.asyncio
    async def test_get_history(self, registry: PromptRegistry) -> None:
        """验证获取版本历史。"""
        await registry.register("t", "v1", tags=["initial"])
        await registry.register("t", "v2", tags=["update"])
        history = await registry.get_history("t")
        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_diff(self, registry: PromptRegistry) -> None:
        """验证版本对比。"""
        await registry.register("t", "第一行\n第二行")
        await registry.register("t", "第一行\n修改了")
        diff = await registry.diff("t", 1, 2)
        assert diff is not None
        assert len(diff) > 0
