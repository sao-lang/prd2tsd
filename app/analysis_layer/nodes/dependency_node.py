"""DependencyAnalyzerNode — LangChain 分析需求间依赖关系。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, DependencyResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=DependencyResult)

DEPENDENCY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个架构师。分析需求间依赖关系。"),
    ("system", "{format_instructions}"),
    ("human", "{reqs_text}"),
])


class DependencyAnalyzerNode:
    """依赖分析节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="dependency")
        self.chain = DEPENDENCY_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行依赖分析节点逻辑。"""
        req_summary = "\n".join(
            f"{r.id}: {r.description[:100]}" for r in state["extracted_requirements"]
        )
        if not req_summary:
            return {**state, "dependency_graph": DependencyResult().dependency_graph}
        try:
            result: DependencyResult = await self.chain.ainvoke({
                "reqs_text": req_summary,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            return {**state, "dependency_graph": result.dependency_graph}
        except Exception:
            return {**state, "dependency_graph": DependencyResult().dependency_graph}
