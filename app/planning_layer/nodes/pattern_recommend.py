"""PatternRecommendNode — LangChain 架构模式推荐。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState
from app.planning_layer.output_models import PatternRecommendResult
from contracts.interfaces import PatternEval

_PARSER = PydanticOutputParser(pydantic_object=PatternRecommendResult)

PATTERN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个软件架构师。基于以下项目需求，推荐 2-3 种适合的架构模式。"),
    ("system", "{format_instructions}"),
    ("human", "项目：{project}\n领域：{domain}\n需求数量：{req_count}"),
])


class PatternRecommendNode:
    """架构模式推荐节点：LangChain 链推荐候选架构模式。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="pattern_recommend")
        self.chain = PATTERN_PROMPT | llm | _PARSER

    async def run(self, state: PlanningState) -> PlanningState:
        ar = state["analysis_result"]

        try:
            result: PatternRecommendResult = await self.chain.ainvoke({
                "project": ar.project_name,
                "domain": ", ".join(ar.domain_tags),
                "req_count": len(ar.requirements),
                "format_instructions": _PARSER.get_format_instructions(),
            })
            patterns = [
                PatternEval(
                    pattern_name=p.pattern_name,
                    match_score=p.match_score,
                    strengths=p.strengths,
                    weaknesses=p.weaknesses,
                    complexity=p.complexity,
                )
                for p in result.patterns
            ]
        except Exception:
            patterns = []

        return {**state, "architecture_patterns": patterns}
