"""ConstraintAnalyzerNode — LangChain 从 PRD 中提取约束条件。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, ConstraintList
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ConstraintList)

CONSTRAINT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个需求分析师。从 PRD 中提取技术/性能/时间/预算/合规/团队约束。"),
    ("system", "{format_instructions}"),
    ("human", "{prd_text}"),
])


class ConstraintAnalyzerNode:
    """约束提取节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="constraint")
        self.chain = CONSTRAINT_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行约束提取节点逻辑。"""
        prd_text = state["prd_raw"][:6000]
        try:
            result: ConstraintList = await self.chain.ainvoke({
                "prd_text": prd_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            return {**state, "extracted_constraints": result.constraints}
        except Exception:
            return {**state, "extracted_constraints": []}
