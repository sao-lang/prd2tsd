"""PromptStorage — 数据库持久化。"""

from __future__ import annotations

from app.core.prompt_registry.models import ABTestConfig, PromptVersion


class PromptVersionNotFoundError(Exception):
    """Prompt 版本不存在异常。"""

    def __init__(self, name: str, version: int | None = None) -> None:
        self.name = name
        self.version = version
        msg = f"Prompt '{name}' 版本 {version} 不存在" if version else f"Prompt '{name}' 不存在"
        super().__init__(msg)


class DuplicateHashError(Exception):
    """重复内容异常。"""

    def __init__(self, name: str, hash_val: str) -> None:
        self.name = name
        self.hash = hash_val
        super().__init__(f"Prompt '{name}' 内容与上一版完全相同 (hash={hash_val[:8]}...)")


class PromptStorage:
    """Prompt 存储 — 内存 + 数据库双写。

    当前为内存实现，后续接入 PostgreSQL。
    """

    def __init__(self) -> None:
        self._store: dict[str, list[PromptVersion]] = {}  # name -> [versions]
        self._ab_configs: dict[str, ABTestConfig] = {}

    async def save(self, pv: PromptVersion) -> None:
        """保存版本。"""
        if pv.name not in self._store:
            self._store[pv.name] = []
        self._store[pv.name].append(pv)

    async def get_latest(self, name: str) -> PromptVersion | None:
        """获取最新版本。"""
        versions = self._store.get(name, [])
        return max(versions, key=lambda v: v.version) if versions else None

    async def get_active(self, name: str) -> PromptVersion | None:
        """获取当前激活版本。"""
        versions = self._store.get(name, [])
        for v in reversed(versions):
            if v.is_active:
                return v
        return None

    async def get_version(self, name: str, version: int) -> PromptVersion | None:
        """获取指定版本。"""
        versions = self._store.get(name, [])
        for v in versions:
            if v.version == version:
                return v
        return None

    async def deactivate(self, name: str) -> None:
        """取消所有版本的激活状态。"""
        versions = self._store.get(name, [])
        for v in versions:
            v.is_active = False

    async def get_next_version(self, name: str) -> int:
        """获取下一个版本号。"""
        latest = await self.get_latest(name)
        return (latest.version + 1) if latest else 1

    async def get_history(self, name: str, limit: int = 20) -> list[PromptVersion]:
        """获取版本历史。"""
        versions = self._store.get(name, [])
        return sorted(versions, key=lambda v: v.version, reverse=True)[:limit]

    async def save_ab_config(self, config: ABTestConfig) -> None:
        """保存 A/B 测试配置。"""
        self._ab_configs[config.prompt_name] = config

    async def get_ab_config(self, name: str) -> ABTestConfig | None:
        """获取 A/B 测试配置。"""
        return self._ab_configs.get(name)
