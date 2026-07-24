"""SecurityComplianceNode — 安全合规检查。"""

from __future__ import annotations

from app.evaluation.models import EvaluationState
from app.evaluation.tools import call_llm, parse_score

SECURITY_PROMPT = """检查以下技术方案的安全合规性：

技术栈：{stack}
组件：{components}

关注：认证授权、数据加密、日志审计、漏洞管理

返回 JSON：{{"score": 7, "findings": [], "critical": []}}
"""


class SecurityComplianceNode:
    """安全合规检查节点。"""

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行安全合规检查。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 dimension_scores.security。
        """
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)
        comp_text = ", ".join(c.name for c in pr.components)

        prompt = SECURITY_PROMPT.format(stack=stack_text, components=comp_text)
        resp = await call_llm(prompt, model="deepseek-v3")
        score = parse_score(resp, "score")

        scores = dict(state.get("dimension_scores", {}))
        scores["security"] = score
        return {**state, "dimension_scores": scores}
