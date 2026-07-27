"""PromptStore — PostgreSQL 持久化。"""

from __future__ import annotations

from app.auth.prompts.models import TenantPrompt


class PromptStore:
    """Prompt 存储 — PostgreSQL 持久化。

    当前为内存实现，后续接入数据库。
    """

    def __init__(self) -> None:
        self._store: dict[str, TenantPrompt] = {}

    def _make_key(self, org_id: str, agent: str, node: str) -> str:
        return f"{org_id}:{agent}:{node}"

    async def get(self, org_id: str, agent: str, node: str) -> TenantPrompt | None:
        """获取租户 Prompt。

        Args:
            org_id: 组织 ID。
            agent: Agent 名称。
            node: Node 名称。

        Returns:
            匹配的 TenantPrompt，不存在返回 None。
        """
        key = self._make_key(org_id, agent, node)
        return self._store.get(key)

    async def upsert(self, prompt: TenantPrompt) -> None:
        """创建或更新租户 Prompt。

        Args:
            prompt: TenantPrompt 实例。
        """
        key = self._make_key(prompt.organization_id, prompt.agent_name, prompt.node_name)
        prompt.updated_at = __import__("datetime").datetime.now()
        self._store[key] = prompt

    async def delete(self, org_id: str, agent: str, node: str) -> bool:
        """删除租户 Prompt。

        Args:
            org_id: 组织 ID。
            agent: Agent 名称。
            node: Node 名称。

        Returns:
            是否删除成功。
        """
        key = self._make_key(org_id, agent, node)
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def list_by_org(self, org_id: str) -> list[TenantPrompt]:
        """列出组织的所有 Prompt。

        Args:
            org_id: 组织 ID。

        Returns:
            Prompt 列表。
        """
        return [p for k, p in self._store.items() if k.startswith(f"{org_id}:")]
