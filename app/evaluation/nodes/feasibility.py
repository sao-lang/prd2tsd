"""FeasibilityEvalNode — 技术可行性评估。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

FEASIBILITY_PROMPT = """评估以下技术方案的技术可行性：

技术栈：{stack}
架构模式：{pattern}

返回 JSON：{{"score": 8, "risks": [], "verdict": "可行"}}
"""


class FeasibilityEvalNode:
    """技术可行性评估节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行可行性评估。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.feasibility。
        """
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)

        prompt = FEASIBILITY_PROMPT.format(
            stack=stack_text,
            pattern=pr.architecture_pattern,
        )
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["feasibility"] = score
        return {**state, "dimension_scores": scores}
