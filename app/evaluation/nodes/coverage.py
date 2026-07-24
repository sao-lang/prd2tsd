"""PRDCoverageCheckNode — PRD 需求覆盖率检查。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

COVERAGE_PROMPT = """你是一个质量评审专家。检查技术方案是否覆盖了所有 PRD 需求。

PRD 需求：
{reqs}

方案内容（摘要）：
{content}

返回覆盖率评分（0-1），以及未覆盖的需求列表。
只需返回 JSON：{{"coverage": 0.85, "missing": ["FR-003"]}}
"""


class PRDCoverageCheckNode:
    """PRD 覆盖率检查节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行覆盖率检查。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.prd_coverage。
        """
        ar = state["analysis_result"]
        reqs_text = "\n".join(f"{r.id}: {r.description[:100]}" for r in ar.requirements)
        content = state["generation_result"].content[:2000]

        prompt = COVERAGE_PROMPT.format(reqs=reqs_text, content=content)
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "coverage")

        scores = dict(state.get("dimension_scores", {}))
        scores["prd_coverage"] = score
        return {**state, "dimension_scores": scores}
