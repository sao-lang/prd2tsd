"""ArchitectureQualityNode — LangChain 架构质量评分。"""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.evaluation.models import EvaluationState
from app.evaluation.tools import ScoreResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=ScoreResult)

ARCH_QUALITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "评估以下架构设计的质量。维度：可扩展性、可维护性、性能、安全性、可测试性。"),
    ("system", "{format_instructions}"),
    ("human", "架构模式：{pattern}\n组件：{components}"),
])


class ArchitectureQualityNode:
    """架构质量评分节点：LangChain 链评分。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="evaluation", layer="evaluation", node="arch_quality")
        self.chain = ARCH_QUALITY_PROMPT | llm | _PARSER

    async def run(self, state: EvaluationState) -> dict[str, Any]:
        """执行架构质量评估节点逻辑。"""
        pr = state["planning_result"]
        comp_text = ", ".join(c.name for c in pr.components)

        try:
            result: ScoreResult = await self.chain.ainvoke({
                "pattern": pr.architecture_pattern,
                "components": comp_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            score = float(result.score)
        except Exception:
            score = 5.0

        dim_scores = dict(state.get("dimension_scores", {}))
        dim_scores["architecture_quality"] = score
        # 只返回增量：并行扇出时其余键会并发写冲突（InvalidUpdateError）
        return {"dimension_scores": dim_scores}
