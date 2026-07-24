"""LegalComplianceEvalNode — ⭐ 法律合规评估。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

LEGAL_PROMPT = """检查以下技术方案的法律合规性：

领域：{domain}

关注：数据保护法规（GDPR/个保法）、开源协议合规、行业监管

返回 JSON：{{"score": 8, "findings": [], "actions": []}}
"""


class LegalComplianceEvalNode:
    """法律合规评估节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行法律合规评估。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.legal_compliance。
        """
        domain = ", ".join(state["analysis_result"].domain_tags)
        prompt = LEGAL_PROMPT.format(domain=domain or "通用")
        resp = await call_llm(prompt, model="gpt-4o-mini")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["legal_compliance"] = score
        return {**state, "dimension_scores": scores}
