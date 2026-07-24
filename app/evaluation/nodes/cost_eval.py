"""CostEvalNode — ⭐ 成本合理性评估。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

COST_EVAL_PROMPT = """评估以下技术方案的成本合理性：

技术栈：{stack}
组件数：{comp_count}

返回 JSON：{{"score": 7, "assessment": "成本合理", "suggestions": []}}
"""


class CostEvalNode:
    """成本合理性评估节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行成本评估。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.cost。
        """
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)

        prompt = COST_EVAL_PROMPT.format(
            stack=stack_text,
            comp_count=len(pr.components),
        )
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["cost"] = score
        return {**state, "dimension_scores": scores}
