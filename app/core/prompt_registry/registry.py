"""Prompt 版本注册器 — 版本化+回滚+A/B 测试。"""

from __future__ import annotations

import difflib
import hashlib
import uuid

from app.core.logger import get_logger
from app.core.prompt_registry.models import PromptVersion
from app.core.prompt_registry.storage import (
    DuplicateHashError,
    PromptStorage,
    PromptVersionNotFoundError,
)

logger = get_logger("prd2tsd.prompt_registry")


class PromptRegistry:
    """Prompt 版本注册器 — 版本化+回滚+A/B 测试。

    每个 Prompt 有独立的版本历史：
    - 版本号自动递增
    - 内容哈希防篡改
    - 支持任意版本回滚
    """

    def __init__(self, storage: PromptStorage | None = None) -> None:
        """初始化 Prompt 注册器。

        Args:
            storage: PromptStorage 实例。
        """
        self.storage = storage or PromptStorage()
        self._active_cache: dict[str, PromptVersion] = {}

    async def register(
        self,
        name: str,
        content: str,
        author: str = "",
        changelog: str = "",
        tags: list[str] | None = None,
    ) -> PromptVersion:
        """注册新版本。

        Args:
            name: Prompt 名称（如 "analysis.requirement"）。
            content: Prompt 文本。
            author: 修改人。
            changelog: 变更说明。
            tags: 标签。

        Returns:
            创建的 PromptVersion。

        Raises:
            DuplicateHashError: 内容与上一版完全相同时抛出。
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        latest = await self.storage.get_latest(name)

        if latest and latest.hash == content_hash:
            raise DuplicateHashError(name, content_hash)

        version = (latest.version + 1) if latest else 1

        if latest and latest.is_active:
            await self.storage.deactivate(name)

        pv = PromptVersion(
            id=str(uuid.uuid4()),
            name=name,
            version=version,
            content=content,
            hash=content_hash,
            author=author,
            changelog=changelog,
            is_active=True,
            tags=tags or [],
        )
        await self.storage.save(pv)
        self._active_cache[name] = pv
        logger.info("Prompt 版本已注册: %s v%d (%s)", name, version, changelog)
        return pv

    async def get_active(self, name: str) -> PromptVersion:
        """获取当前激活版本。

        Args:
            name: Prompt 名称。

        Returns:
            当前激活的 PromptVersion。

        Raises:
            PromptVersionNotFoundError: 未找到。
        """
        cached = self._active_cache.get(name)
        if cached:
            return cached
        pv = await self.storage.get_active(name)
        if pv is None:
            raise PromptVersionNotFoundError(name)
        self._active_cache[name] = pv
        return pv

    async def rollback(self, name: str, version: int) -> PromptVersion:
        """回滚到指定版本。

        Args:
            name: Prompt 名称。
            version: 目标版本号。

        Returns:
            新创建的 PromptVersion（新版本号）。
        """
        target = await self.storage.get_version(name, version)
        if target is None:
            raise PromptVersionNotFoundError(name, version)

        await self.storage.deactivate(name)
        target.is_active = True
        target.version = await self.storage.get_next_version(name)
        target.changelog = f"回滚到 v{version}"
        # 创建新副本
        new_pv = target.model_copy(deep=True)
        new_pv.id = str(uuid.uuid4())
        await self.storage.save(new_pv)
        self._active_cache[name] = new_pv
        logger.info("Prompt 已回滚: %s → v%d (new v%d)", name, version, new_pv.version)
        return new_pv

    async def get_history(self, name: str, limit: int = 20) -> list[PromptVersion]:
        """获取版本历史。

        Args:
            name: Prompt 名称。
            limit: 返回数量。

        Returns:
            版本历史列表。
        """
        return await self.storage.get_history(name, limit=limit)

    async def diff(self, name: str, v1: int, v2: int) -> str:
        """对比两个版本的差异（类 git diff）。

        Args:
            name: Prompt 名称。
            v1: 版本号 A。
            v2: 版本号 B。

        Returns:
            unified diff 格式的差异文本。
        """
        pv1 = await self.storage.get_version(name, v1)
        pv2 = await self.storage.get_version(name, v2)
        if not pv1:
            raise PromptVersionNotFoundError(name, v1)
        if not pv2:
            raise PromptVersionNotFoundError(name, v2)

        lines1 = pv1.content.splitlines()
        lines2 = pv2.content.splitlines()
        return "\n".join(difflib.unified_diff(lines1, lines2, f"v{v1}", f"v{v2}"))

    async def resolve_ab_test(self, name: str, user_id: str) -> PromptVersion:
        """A/B 测试路由 — 根据用户 ID 哈希决定走哪个版本。

        Args:
            name: Prompt 名称。
            user_id: 用户 ID。

        Returns:
            路由到的 PromptVersion。
        """
        config = await self.storage.get_ab_config(name)
        if not config or not config.is_active:
            return await self.get_active(name)

        user_hash = (hash(user_id) % 100) / 100.0
        if user_hash < config.traffic_split:
            return await self.storage.get_version(name, config.version_a)  # type: ignore[return-value]
        else:
            return await self.storage.get_version(name, config.version_b)  # type: ignore[return-value]
