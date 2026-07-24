"""RiskQuantifierNode — ⭐ 风险量化（概率×影响矩阵）。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

RISK_PROMPT = """你是一个风险管理专家。为以下项目进行风险量化分析。

项目：{project}
技术栈：{stack}
组件数：{comp_count}

返回 JSON 数组：
[
  {{
    "risk": "数据库性能瓶颈",
    "probability": 0.3,
    "impact": 0.8,
    "risk_score": 0.24,
    "mitigation": "读写分离 + 缓存"
  }}
]
"""


class RiskQuantifierNode:
    """风险量化节点：概率×影响矩阵。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行风险量化。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        ar = state["analysis_result"]
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))
        prompt = RISK_PROMPT.format(
            project=ar.project_name,
            stack=stack_names or "待确定",
            comp_count=len(state.get("component_decomposition", [])),
        )
        await call_llm_async(prompt, model="deepseek-v3")
        return state
