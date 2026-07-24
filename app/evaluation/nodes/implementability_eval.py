"""ImplementabilityEvalNode — ⭐ 可实施性评估。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

IMPL_PROMPT = """评估以下技术方案的可实施性：

团队技能要求：{skills}
实施周期：{timeline}

返回 JSON：{{"score": 7, "blockers": [], "suggestions": []}}
"""


class ImplementabilityEvalNode:
    """可实施性评估节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行可实施性评估。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.implementability。
        """
        prompt = IMPL_PROMPT.format(skills="见技能分析章节", timeline="见时间线章节")
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["implementability"] = score
        return {**state, "dimension_scores": scores}
