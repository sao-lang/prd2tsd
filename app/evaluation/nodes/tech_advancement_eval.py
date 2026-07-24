"""TechAdvancementEvalNode — ⭐ 技术先进性评估。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

TECH_ADV_PROMPT = """评估以下技术方案的技术先进性：

技术栈：{stack}
架构模式：{pattern}

评估：技术成熟度、社区活跃度、生态完善度、创新性

返回 JSON：{{"score": 7, "detail": "使用了主流成熟技术"}}
"""


class TechAdvancementEvalNode:
    """技术先进性评估节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行技术先进性评估。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.tech_advancement。
        """
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)

        prompt = TECH_ADV_PROMPT.format(
            stack=stack_text,
            pattern=pr.architecture_pattern,
        )
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["tech_advancement"] = score
        return {**state, "dimension_scores": scores}
