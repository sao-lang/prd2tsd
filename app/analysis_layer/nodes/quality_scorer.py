"""RequirementQualityNode — LangChain 需求质量评分。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, QualityResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=QualityResult)

QUALITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个需求质量评审专家。对需求列表进行评分。"),
    ("system", "{format_instructions}"),
    ("human", "{reqs_text}"),
])


class RequirementQualityNode:
    """需求质量评分节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="quality")
        self.chain = QUALITY_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        reqs_text = "\n".join(
            f"{r.id} [{r.priority}] {r.description[:100]}" for r in state["extracted_requirements"]
        )
        if not reqs_text:
            return {**state, "confidence": 0.0}
        try:
            result: QualityResult = await self.chain.ainvoke({
                "reqs_text": reqs_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            overall = result.score / 10.0 if result.score > 0 else 0.5
            return {**state, "confidence": overall}
        except Exception:
            return {**state, "confidence": 0.5}
