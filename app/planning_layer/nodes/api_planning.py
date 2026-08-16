"""APIPlanningNode — LangChain API 接口规划。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState

API_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个 API 架构师。为以下项目规划 API 接口草稿。"),
    ("system", "列出核心 API 端点及其用途、请求方法和响应格式。"),
    ("human", "项目：{project}\n组件：{components}"),
])


class APIPlanningNode:
    """API 规划节点：LangChain 链生成 API 接口草稿。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="api_planning")
        self.chain = API_PROMPT | llm

    async def run(self, state: PlanningState) -> PlanningState:
        """执行 API 规划节点逻辑。"""
        comps = state.get("component_decomposition", [])
        comp_names = ", ".join(c.name for c in comps[:5])
        ar = state["analysis_result"]
        result = await self.chain.ainvoke({
            "project": ar.project_name,
            "components": comp_names or "待定",
        })
        response = result.content if hasattr(result, "content") else str(result)

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["api_plan"] = response
        return {**state, "node_outputs": node_outputs}
