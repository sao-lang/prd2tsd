"""CostEstimatorNode — LangChain 3 种成本方案估算。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState
from app.planning_layer.output_models import CostEstimateResult

_PARSER = PydanticOutputParser(pydantic_object=CostEstimateResult)

COST_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个成本估算专家。为以下项目估算 3 种成本方案（低配/标准/高可用）。"),
    ("system", "{format_instructions}"),
    ("human", "项目：{project}\n组件数：{comp_count}\n技术栈：{stack}"),
])


class CostEstimatorNode:
    """成本估算节点：LangChain 链生成 3 种部署方案成本估算。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="cost_estimator")
        self.chain = COST_PROMPT | llm | _PARSER

    async def run(self, state: PlanningState) -> PlanningState:
        ar = state["analysis_result"]
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))
        node_outputs = dict(state.get("node_outputs", {}))

        try:
            result: CostEstimateResult = await self.chain.ainvoke({
                "project": ar.project_name,
                "comp_count": len(state.get("component_decomposition", [])),
                "stack": stack_names or "待确定",
                "format_instructions": _PARSER.get_format_instructions(),
            })
            node_outputs["cost_estimates"] = result.model_dump()
        except Exception:
            node_outputs["cost_estimates"] = {}

        return {**state, "node_outputs": node_outputs}
