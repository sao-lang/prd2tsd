"""ConsistencyEvalNode — 方案内部一致性评测。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

CONSISTENCY_PROMPT = """检查以下技术方案是否存在内部矛盾或不一致：

架构模式：{pattern}
技术栈：{stack}
组件：{components}

返回 JSON：{{"score": 8, "issues": [], "detail": "方案整体一致"}}
"""


class ConsistencyEvalNode:
    """内部一致性评测节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行一致性评测。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.consistency。
        """
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)
        comp_text = ", ".join(c.name for c in pr.components)

        prompt = CONSISTENCY_PROMPT.format(
            pattern=pr.architecture_pattern,
            stack=stack_text,
            components=comp_text,
        )
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["consistency"] = score
        return {**state, "dimension_scores": scores}
