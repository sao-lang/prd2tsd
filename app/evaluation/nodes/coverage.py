"""PRDCoverageCheckNode — LangChain PRD 需求覆盖率检查。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.evaluation.models import EvaluationState
from app.evaluation.tools import ScoreResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ScoreResult)

COVERAGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个质量评审专家。检查技术方案是否覆盖了所有 PRD 需求。"),
    ("system", "{format_instructions}"),
    ("human", "PRD 需求：\n{reqs}\n\n方案内容（摘要）：\n{content}"),
])


class PRDCoverageCheckNode:
    """PRD 覆盖率检查节点：LangChain 链评分。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="evaluation", layer="evaluation", node="prd_coverage")
        self.chain = COVERAGE_PROMPT | llm | _PARSER

    async def run(self, state: EvaluationState) -> EvaluationState:
        ar = state["analysis_result"]
        reqs_text = "\n".join(f"{r.id}: {r.description[:100]}" for r in ar.requirements)
        content = state["generation_result"].content[:2000]

        try:
            result: ScoreResult = await self.chain.ainvoke({
                "reqs": reqs_text,
                "content": content,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            score = float(result.score)
        except Exception:
            score = 5.0

        dim_scores = dict(state.get("dimension_scores", {}))
        dim_scores["prd_coverage"] = score
        return {**state, "dimension_scores": dim_scores}
