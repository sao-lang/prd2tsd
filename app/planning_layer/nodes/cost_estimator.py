"""CostEstimatorNode — ⭐ 3 种成本方案估算。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

COST_PROMPT = """你是一个成本估算专家。为以下项目估算 3 种成本方案。

项目：{project}
组件数：{comp_count}
技术栈：{stack}

返回 JSON：
{{
  "low_cost": {{"monthly": 5000, "desc": "最低配置", "risks": ["性能瓶颈"]}},
  "standard": {{"monthly": 15000, "desc": "标准配置", "risks": []}},
  "high_availability": {{"monthly": 40000, "desc": "高可用配置", "risks": ["成本高"]}}
}}
"""


class CostEstimatorNode:
    """成本估算节点：3 种部署方案成本估算。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行成本估算。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        ar = state["analysis_result"]
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))
        prompt = COST_PROMPT.format(
            project=ar.project_name,
            comp_count=len(state.get("component_decomposition", [])),
            stack=stack_names or "待确定",
        )
        await call_llm_async(prompt, model="deepseek-v3")
        return state
