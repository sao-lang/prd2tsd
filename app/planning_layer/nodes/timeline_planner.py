"""TimelinePlannerNode — LangChain 时间线规划。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState

TIMELINE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个项目管理专家。为以下项目生成时间线规划和里程碑。"),
    ("system", "输出格式：用文本描述各阶段（调研/开发/测试/部署）的时间安排和关键里程碑。"),
    ("human", "项目：{project}\n组件数：{comp_count}"),
])


class TimelinePlannerNode:
    """时间线规划节点：LangChain 链生成甘特图 + 里程碑。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="timeline_planner")
        self.chain = TIMELINE_PROMPT | llm

    async def run(self, state: PlanningState) -> PlanningState:
        """执行时间线规划节点逻辑。"""
        ar = state["analysis_result"]
        result = await self.chain.ainvoke({
            "project": ar.project_name,
            "comp_count": len(state.get("component_decomposition", [])),
        })
        response = result.content if hasattr(result, "content") else str(result)

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["timeline"] = response
        return {**state, "node_outputs": node_outputs}
