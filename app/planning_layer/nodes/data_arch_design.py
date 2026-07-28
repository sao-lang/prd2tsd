"""DataArchDesignNode — LangChain 数据架构设计。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState

DATA_ARCH_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个数据架构师。为以下项目设计数据架构。"),
    ("system", "说明数据库选型、数据流、ER 关系等。"),
    ("human", "项目：{project}\n组件：{components}"),
])


class DataArchDesignNode:
    """数据架构设计节点：LangChain 链生成数据架构方案。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="data_arch_design")
        self.chain = DATA_ARCH_PROMPT | llm

    async def run(self, state: PlanningState) -> PlanningState:
        comps = state.get("component_decomposition", [])
        comp_names = ", ".join(c.name for c in comps[:5])
        ar = state["analysis_result"]
        result = await self.chain.ainvoke({
            "project": ar.project_name,
            "components": comp_names or "待定",
        })
        response = result.content if hasattr(result, "content") else str(result)

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["data_arch"] = response
        return {**state, "node_outputs": node_outputs}
