"""TechStackSelectNode — LangChain 按维度分批选择技术栈。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState
from app.planning_layer.output_models import TechStackResult
from contracts.interfaces import TechChoiceDetail

_PARSER = PydanticOutputParser(pydantic_object=TechStackResult)

TECH_STACK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个技术选型专家。为以下项目按维度选择技术栈。"),
    ("system",
     "维度包括：backend_framework, database_primary, cache, message_queue, "
     "frontend, testing, ci_cd, monitoring"),
    ("system", "{format_instructions}"),
    ("human", "项目：{project}\n架构模式：{pattern}\n领域：{domain}"),
])


class TechStackSelectNode:
    """技术栈选型节点：LangChain 链按维度决策。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="tech_stack_select")
        self.chain = TECH_STACK_PROMPT | llm | _PARSER

    async def run(self, state: PlanningState) -> PlanningState:
        ar = state["analysis_result"]

        try:
            result: TechStackResult = await self.chain.ainvoke({
                "project": ar.project_name,
                "pattern": state.get("selected_pattern", "未确定"),
                "domain": ", ".join(ar.domain_tags),
                "format_instructions": _PARSER.get_format_instructions(),
            })
            choices = [
                TechChoiceDetail(
                    dimension=c.dimension,
                    recommendation=c.recommendation,
                    reason=c.reason,
                    alternatives=c.alternatives,
                    risks=c.risks,
                )
                for c in result.choices
            ]
        except Exception:
            choices = []

        return {**state, "tech_stack_choices": choices}
