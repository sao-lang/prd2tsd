"""DeploymentPlanningNode — LangChain 部署方案规划。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState

DEPLOY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个 DevOps 专家。为以下项目设计部署方案。"),
    ("system", "说明容器化方案、CI/CD 流程、环境规划等。"),
    ("human", "项目：{project}\n架构模式：{pattern}"),
])


class DeploymentPlanningNode:
    """部署方案规划节点：LangChain 链生成部署方案。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="deployment_planning")
        self.chain = DEPLOY_PROMPT | llm

    async def run(self, state: PlanningState) -> PlanningState:
        ar = state["analysis_result"]
        result = await self.chain.ainvoke({
            "project": ar.project_name,
            "pattern": state.get("selected_pattern", "分层架构"),
        })
        response = result.content if hasattr(result, "content") else str(result)

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["deployment_plan"] = response
        return {**state, "node_outputs": node_outputs}
