"""ArchitectureQualityNode — 架构质量评分。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

ARCH_QUALITY_PROMPT = """评估以下架构设计的质量：

架构模式：{pattern}
组件：{components}

评估维度：可扩展性、可维护性、性能、安全性、可测试性

返回 JSON：{{"score": 7.5, "strengths": [], "weaknesses": []}}
"""


class ArchitectureQualityNode:
    """架构质量评分节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行架构质量评分。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.architecture_quality。
        """
        pr = state["planning_result"]
        comp_text = ", ".join(c.name for c in pr.components)

        prompt = ARCH_QUALITY_PROMPT.format(
            pattern=pr.architecture_pattern,
            components=comp_text,
        )
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["architecture_quality"] = score
        return {**state, "dimension_scores": scores}
