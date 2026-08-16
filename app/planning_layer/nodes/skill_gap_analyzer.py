"""SkillGapAnalyzerNode — LangChain 技能缺口分析。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState

SKILL_GAP_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个团队管理专家。分析实现以下项目所需的技能缺口。"),
    ("system", "分析当前常见团队技能与项目需求之间的差距，列出需要招聘或培训的技能。"),
    ("human", "技术栈：{stack}"),
])


class SkillGapAnalyzerNode:
    """技能缺口分析节点：LangChain 链分析技能需求。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="skill_gap_analyzer")
        self.chain = SKILL_GAP_PROMPT | llm

    async def run(self, state: PlanningState) -> PlanningState:
        """执行技能缺口分析节点逻辑。"""
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))
        if not stack_names:
            return state

        result = await self.chain.ainvoke({"stack": stack_names})
        response = result.content if hasattr(result, "content") else str(result)

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["skill_gaps"] = response
        return {**state, "node_outputs": node_outputs}
