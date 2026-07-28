"""StakeholderAnalyzerNode — 干系人分析。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, StakeholderList
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=StakeholderList)

STAKEHOLDER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个项目经理。从 PRD 中提取干系人及其关注点。"),
    ("system", "{format_instructions}"),
    ("human", "{prd_text}"),
])


class StakeholderAnalyzerNode:
    """干系人分析节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="stakeholder")
        self.chain = STAKEHOLDER_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        prd_text = state["prd_raw"][:4000]
        try:
            result: StakeholderList = await self.chain.ainvoke({
                "prd_text": prd_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            return {**state, "stakeholders": result.stakeholders}
        except Exception:
            return {**state, "stakeholders": []}
