"""EffortEstimatorNode — COCOMO II + LangChain 工作量估算。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, EffortResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=EffortResult)

EFFORT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个软件估算专家。按 COCOMO II 模型估算工作量。"),
    ("system", "{format_instructions}"),
    ("human", "{reqs_text}"),
])


class EffortEstimatorNode:
    """工作量估算节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="effort")
        self.chain = EFFORT_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行工作量估算节点逻辑。"""
        reqs_text = "\n".join(
            f"{r.id} [{r.priority}] {r.category}: {r.description[:120]}"
            for r in state["extracted_requirements"]
        )
        if not reqs_text:
            return state
        try:
            result: EffortResult = await self.chain.ainvoke({
                "reqs_text": reqs_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            eff_conf = result.confidence if hasattr(result, "confidence") else 0.5
            return {**state, "confidence": (state["confidence"] + eff_conf) / 2.0}
        except Exception:
            return state
