"""SkillGapAnalyzerNode — ⭐ 技能缺口分析。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

SKILL_GAP_PROMPT = """你是一个团队管理专家。分析实现以下项目所需的技能缺口。

技术栈：{stack}

分析当前常见团队技能与项目需求之间的差距，
列出需要招聘或培训的技能。
"""


class SkillGapAnalyzerNode:
    """技能缺口分析节点。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行技能缺口分析。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))
        if not stack_names:
            return state

        prompt = SKILL_GAP_PROMPT.format(stack=stack_names)
        await call_llm_async(prompt, model="deepseek-v3")
        return state
