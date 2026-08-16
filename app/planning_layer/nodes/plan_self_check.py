"""PlanSelfCheckNode — LangChain 自检节点。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import get_logger
from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState
from app.planning_layer.output_models import SelfCheckResult

logger = get_logger("prd2tsd.planning.plan_self_check")

_PARSER = PydanticOutputParser(pydantic_object=SelfCheckResult)

SELF_CHECK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "检查以下规划结果是否完整可用。"),
    ("system", "{format_instructions}"),
    ("human", "架构模式：{pattern}\n技术栈：{stack}\n组件数：{comp_count}"),
])


class PlanSelfCheckNode:
    """自检节点：LangChain 链检查规划完整性。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="plan_self_check")
        self.chain = SELF_CHECK_PROMPT | llm | _PARSER

    async def run(self, state: PlanningState) -> PlanningState:
        """执行规划结果自检节点逻辑。"""
        stack_names = ", ".join(t.recommendation for t in state.get("tech_stack_choices", []))

        try:
            result: SelfCheckResult = await self.chain.ainvoke({
                "pattern": state.get("selected_pattern", "未确定"),
                "stack": stack_names or "未选择",
                "comp_count": len(state.get("component_decomposition", [])),
                "format_instructions": _PARSER.get_format_instructions(),
            })
            passed = result.passed
            issues = result.issues
        except Exception as exc:
            logger.warning("规划自检执行失败: %s", exc)
            passed = False
            issues = ["自检执行失败"]

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["self_check_passed"] = passed
        node_outputs["self_check_result"] = {"passed": passed, "issues": issues}

        return {
            **state,
            "node_outputs": node_outputs,
            "self_check_attempts": state.get("self_check_attempts", 0) + 1,
        }
