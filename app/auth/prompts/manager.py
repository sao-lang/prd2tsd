"""Prompt 管理器 — 按租户+Agent+Node 加载 Prompt。

查找优先级：
1. 租户自定义 Prompt（organization_id + agent_name + node_name）
2. 租户默认 Prompt（organization_id + agent_name + "*"）
3. 系统默认 Prompt（硬编码兜底）
"""

from __future__ import annotations

from app.auth.prompts.models import TenantPrompt
from app.auth.prompts.renderer import PromptRenderer
from app.auth.prompts.store import PromptStore

DEFAULT_PROMPTS: dict[str, str] = {
    "analysis:requirement": "你是一个需求分析专家。从以下 PRD 中提取功能需求和非功能需求。",
    "planning:pattern": "你是一个架构设计专家。推荐适合的架构模式。",
    "generation:outline": "你是一个技术文档作者。生成技术方案大纲。",
    "evaluation:scoring": "你是一个技术评审专家。对以下方案进行评分。",
}


class PromptManager:
    """Prompt 管理器 — 按租户+Agent+Node 加载 Prompt。

    查找优先级：
    1. 租户自定义 Prompt
    2. 租户默认 Prompt（Agent 级通配）
    3. 系统默认 Prompt（硬编码兜底）
    """

    def __init__(self, store: PromptStore | None = None) -> None:
        """初始化 Prompt 管理器。

        Args:
            store: PromptStore 实例（可选）。
        """
        self.store = store or PromptStore()
        self.renderer = PromptRenderer()
        self._cache: dict[str, TenantPrompt] = {}

    async def get_prompt(
        self,
        organization_id: str,
        agent_name: str,
        node_name: str,
        extra_vars: dict[str, str] | None = None,
    ) -> str:
        """获取渲染后的 Prompt。

        Args:
            organization_id: 组织 ID。
            agent_name: Agent 名称。
            node_name: Node 名称。
            extra_vars: 额外变量（覆盖默认值）。

        Returns:
            渲染后的 System Prompt 文本。
        """
        template = await self._find_template(organization_id, agent_name, node_name)
        if template is None:
            return self._get_default_prompt(agent_name, node_name)

        variables = {**template.variables, **(extra_vars or {})}
        return self.renderer.render(template.template, variables)

    async def _find_template(
        self,
        org_id: str,
        agent: str,
        node: str,
    ) -> TenantPrompt | None:
        """按优先级查找模板。"""
        cache_key = f"{org_id}:{agent}:{node}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        # 优先级 1: 精确匹配
        template = await self.store.get(org_id, agent, node)
        if template:
            self._cache[cache_key] = template
            return template

        # 优先级 2: Agent 级通配
        template = await self.store.get(org_id, agent, "*")
        if template:
            self._cache[cache_key] = template
            return template

        return None

    async def upsert_template(self, prompt: TenantPrompt) -> None:
        """创建或更新租户 Prompt。

        Args:
            prompt: TenantPrompt 实例。
        """
        await self.store.upsert(prompt)
        self._cache.clear()

    async def delete_template(self, org_id: str, agent: str, node: str) -> bool:
        """删除租户 Prompt（回退到系统默认）。

        Args:
            org_id: 组织 ID。
            agent: Agent 名称。
            node: Node 名称。

        Returns:
            是否删除成功。
        """
        result = await self.store.delete(org_id, agent, node)
        self._cache.clear()
        return result

    @staticmethod
    def _get_default_prompt(agent: str, node: str) -> str:
        """获取系统默认 Prompt（硬编码兜底）。"""
        return DEFAULT_PROMPTS.get(f"{agent}:{node}", "你是一个 AI 助手。")

    def invalidate_cache(self, org_id: str | None = None) -> None:
        """清除缓存（API 更新配置后调用）。

        Args:
            org_id: 组织 ID（可选，为 None 时清除全部）。
        """
        if org_id:
            self._cache = {k: v for k, v in self._cache.items() if not k.startswith(f"{org_id}:")}
        else:
            self._cache.clear()
