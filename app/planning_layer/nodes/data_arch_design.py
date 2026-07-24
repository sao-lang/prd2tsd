"""DataArchDesignNode — 数据架构设计。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

DATA_ARCH_PROMPT = """为以下项目设计数据架构。

项目：{project}
组件：{components}

说明数据库选型、数据流、ER 关系等。
"""


class DataArchDesignNode:
    """数据架构设计节点。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行数据架构设计。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        comps = state.get("component_decomposition", [])
        comp_names = ", ".join(c.name for c in comps[:5])
        ar = state["analysis_result"]
        prompt = DATA_ARCH_PROMPT.format(project=ar.project_name, components=comp_names or "待定")
        await call_llm_async(prompt, model="deepseek-v3")
        return state
