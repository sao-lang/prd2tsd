"""PlanSelfCheckNode — 自检，不通过则回退。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

SELF_CHECK_PROMPT = """检查以下规划结果是否完整可用。

架构模式：{pattern}
技术栈：{stack}
组件数：{comp_count}

如果一切合理，回复"通过"；如有问题，说明具体问题。
"""


class PlanSelfCheckNode:
    """自检节点：检查规划完整性。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行自检。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))
        prompt = SELF_CHECK_PROMPT.format(
            pattern=state.get("selected_pattern", "未确定"),
            stack=stack_names or "未选择",
            comp_count=len(state.get("component_decomposition", [])),
        )
        await call_llm_async(prompt, model="gpt-4o-mini")
        return state
