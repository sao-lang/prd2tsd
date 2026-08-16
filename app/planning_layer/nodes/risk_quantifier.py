"""RiskQuantifierNode — LangChain 风险量化（概率×影响矩阵）。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState
from app.planning_layer.output_models import RiskQuantifyResult

_PARSER = PydanticOutputParser(pydantic_object=RiskQuantifyResult)

RISK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个风险管理专家。为以下项目进行风险量化分析（概率×影响矩阵）。"),
    ("system", "{format_instructions}"),
    ("human", "项目：{project}\n技术栈：{stack}\n组件数：{comp_count}"),
])


class RiskQuantifierNode:
    """风险量化节点：LangChain 链生成概率×影响矩阵。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="risk_quantifier")
        self.chain = RISK_PROMPT | llm | _PARSER

    async def run(self, state: PlanningState) -> PlanningState:
        """执行风险量化节点逻辑。"""
        ar = state["analysis_result"]
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))
        node_outputs = dict(state.get("node_outputs", {}))

        try:
            result: RiskQuantifyResult = await self.chain.ainvoke({
                "project": ar.project_name,
                "stack": stack_names or "待确定",
                "comp_count": len(state.get("component_decomposition", [])),
                "format_instructions": _PARSER.get_format_instructions(),
            })
            node_outputs["risks"] = [r.model_dump() for r in result.risks]
        except Exception:
            node_outputs["risks"] = []

        return {**state, "node_outputs": node_outputs}
