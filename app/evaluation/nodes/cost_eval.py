"""CostEvalNode — LangChain 成本合理性评估。"""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.evaluation.models import EvaluationState
from app.evaluation.tools import ScoreResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ScoreResult)

COST_EVAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "评估以下技术方案的成本合理性。"),
    ("system", "{format_instructions}"),
    ("human", "技术栈：{stack}\n组件数：{comp_count}"),
])


class CostEvalNode:
    """成本评估节点：LangChain 链评分。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="evaluation", layer="evaluation", node="cost_eval")
        self.chain = COST_EVAL_PROMPT | llm | _PARSER

    async def run(self, state: EvaluationState) -> dict[str, Any]:
        """执行成本合理性评估节点逻辑。"""
        pr = state["planning_result"]
        stack_text = ", ".join(t.recommendation for t in pr.tech_stack)

        try:
            result: ScoreResult = await self.chain.ainvoke({
                "stack": stack_text,
                "comp_count": len(pr.components),
                "format_instructions": _PARSER.get_format_instructions(),
            })
            score = float(result.score)
        except Exception:
            score = 5.0

        dim_scores = dict(state.get("dimension_scores", {}))
        dim_scores["cost"] = score
        # 只返回增量：并行扇出时其余键会并发写冲突（InvalidUpdateError）
        return {"dimension_scores": dim_scores}
