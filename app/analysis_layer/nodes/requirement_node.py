"""RequirementExtractorNode — LangChain LLM 从 PRD 中提取需求。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, RequirementList
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=RequirementList)

REQUIREMENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个需求分析师。从 PRD 中提取功能需求和非功能需求。"),
    ("system", "{format_instructions}"),
    ("human", "{prd_text}"),
])


class RequirementExtractorNode:
    """需求提取节点：LangChain 链从 PRD 中提取需求列表。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="requirement")
        self.chain = REQUIREMENT_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行需求提取节点逻辑。"""
        prd_text = state["prd_raw"][:8000]
        try:
            result: RequirementList = await self.chain.ainvoke({
                "prd_text": prd_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            return {**state, "extracted_requirements": result.requirements}
        except Exception:
            return {**state, "extracted_requirements": []}
