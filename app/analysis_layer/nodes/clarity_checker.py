"""ClarityCheckerNode — 检查 PRD 清晰度。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, ClarityResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ClarityResult)

CLARITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "检查需求描述是否清晰、无歧义。列出有问题的需求。"),
    ("system", "{format_instructions}"),
    ("human", "{reqs_text}"),
])


class ClarityCheckerNode:
    """清晰度检查节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="clarity")
        self.chain = CLARITY_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行需求清晰度检查。"""
        reqs_text = "\n".join(
            f"{r.id}: {r.description[:150]}" for r in state["extracted_requirements"]
        )
        if not reqs_text:
            return state
        try:
            result: ClarityResult = await self.chain.ainvoke({
                "reqs_text": reqs_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            return {**state, "clarity_issues": result.issues}
        except Exception:
            return state
