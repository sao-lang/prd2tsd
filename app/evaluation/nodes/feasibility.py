"""FeasibilityEvalNode — LangChain 技术可行性评估。"""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.evaluation.models import EvaluationState
from app.evaluation.tools import ScoreResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ScoreResult)

FEASIBILITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "评估以下技术方案的技术可行性。"),
    ("system", "{format_instructions}"),
    ("human", "技术栈：{stack}\n架构模式：{pattern}"),
])


class FeasibilityEvalNode:
    """可行性评估节点：LangChain 链评分。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="evaluation", layer="evaluation", node="feasibility")
        self.chain = FEASIBILITY_PROMPT | llm | _PARSER

    async def run(self, state: EvaluationState) -> dict[str, Any]:
        """执行技术可行性评估节点逻辑。"""
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)

        try:
            result: ScoreResult = await self.chain.ainvoke({
                "stack": stack_text,
                "pattern": pr.architecture_pattern,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            score = float(result.score)
        except Exception:
            score = 5.0

        dim_scores = dict(state.get("dimension_scores", {}))
        dim_scores["feasibility"] = score
        # 只返回增量：并行扇出时其余键会并发写冲突（InvalidUpdateError）
        return {"dimension_scores": dim_scores}
