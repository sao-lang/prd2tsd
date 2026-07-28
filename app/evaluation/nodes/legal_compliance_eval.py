"""LegalComplianceEvalNode — LangChain 法律合规评估。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.evaluation.models import EvaluationState
from app.evaluation.tools import ScoreResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ScoreResult)

LEGAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "检查以下技术方案的法律合规性。关注：数据保护法规（GDPR/个保法）、开源协议合规、行业监管。"),
    ("system", "{format_instructions}"),
    ("human", "领域：{domain}"),
])


class LegalComplianceEvalNode:
    """法律合规评估节点：LangChain 链评分。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="evaluation", layer="evaluation", node="legal_compliance")
        self.chain = LEGAL_PROMPT | llm | _PARSER

    async def run(self, state: EvaluationState) -> EvaluationState:
        ar = state["analysis_result"]
        domain = ", ".join(ar.domain_tags) if hasattr(ar, "domain_tags") else "通用"

        try:
            result: ScoreResult = await self.chain.ainvoke({
                "domain": domain,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            score = float(result.score)
        except Exception:
            score = 5.0

        dim_scores = dict(state.get("dimension_scores", {}))
        dim_scores["legal_compliance"] = score
        return {**state, "dimension_scores": dim_scores}
