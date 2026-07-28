"""SecurityComplianceNode — LangChain 安全合规检查。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.evaluation.models import EvaluationState
from app.evaluation.tools import ScoreResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ScoreResult)

SECURITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "检查以下技术方案的安全合规性。关注：认证授权、数据加密、日志审计、漏洞管理。"),
    ("system", "{format_instructions}"),
    ("human", "技术栈：{stack}\n组件：{components}"),
])


class SecurityComplianceNode:
    """安全合规检查节点：LangChain 链评分。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="evaluation", layer="evaluation", node="security_compliance")
        self.chain = SECURITY_PROMPT | llm | _PARSER

    async def run(self, state: EvaluationState) -> EvaluationState:
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)
        comp_text = ", ".join(c.name for c in pr.components)

        try:
            result: ScoreResult = await self.chain.ainvoke({
                "stack": stack_text,
                "components": comp_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            score = float(result.score)
        except Exception:
            score = 5.0

        dim_scores = dict(state.get("dimension_scores", {}))
        dim_scores["security"] = score
        return {**state, "dimension_scores": dim_scores}
