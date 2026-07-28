"""ImplementabilityEvalNode — LangChain 可实施性评估。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.evaluation.models import EvaluationState
from app.evaluation.tools import ScoreResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ScoreResult)

IMPL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "评估以下技术方案的可实施性。考虑团队技能要求和实施周期。"),
    ("system", "{format_instructions}"),
    ("human", "团队技能要求：{skills}\n实施周期：{timeline}"),
])


class ImplementabilityEvalNode:
    """可实施性评估节点：LangChain 链评分。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="evaluation", layer="evaluation", node="implementability")
        self.chain = IMPL_PROMPT | llm | _PARSER

    async def run(self, state: EvaluationState) -> EvaluationState:
        try:
            # 从 state 提取技能和时间线信息（如果可用）
            node_outputs = state.get("node_outputs", {})
            skills = str(node_outputs.get("skill_gaps", "见技能分析章节"))
            timeline = str(node_outputs.get("timeline", "见时间线章节"))

            result: ScoreResult = await self.chain.ainvoke({
                "skills": skills[:1000],
                "timeline": timeline[:1000],
                "format_instructions": _PARSER.get_format_instructions(),
            })
            score = float(result.score)
        except Exception:
            score = 5.0

        dim_scores = dict(state.get("dimension_scores", {}))
        dim_scores["implementability"] = score
        return {**state, "dimension_scores": dim_scores}
