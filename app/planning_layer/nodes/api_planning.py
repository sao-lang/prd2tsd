"""APIPlanningNode — API 规划草稿。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

API_PROMPT = """为以下项目规划 API 接口草稿。

项目：{project}
组件：{components}

列出核心 API 端点及其用途。
"""


class APIPlanningNode:
    """API 规划节点。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行 API 规划。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        comps = state.get("component_decomposition", [])
        comp_names = ", ".join(c.name for c in comps[:5])
        ar = state["analysis_result"]
        prompt = API_PROMPT.format(project=ar.project_name, components=comp_names or "待定")
        await call_llm_async(prompt, model="deepseek-v3")
        return state
