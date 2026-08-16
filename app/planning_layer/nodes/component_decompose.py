"""ComponentDecomposeNode — LangChain 需求→组件分解。"""

from __future__ import annotations

from typing import Literal, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.planning_layer.models import PlanningState
from app.planning_layer.output_models import ComponentDecomposeResult
from contracts.interfaces import ComponentDetail

_PARSER = PydanticOutputParser(pydantic_object=ComponentDecomposeResult)

DECOMPOSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个软件架构师。将以下需求分解为系统组件。"),
    ("system", "{format_instructions}"),
    ("human", "架构模式：{pattern}\n需求：\n{reqs}"),
])


class ComponentDecomposeNode:
    """组件分解节点：LangChain 链需求→组件。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="planning", layer="planning", node="component_decompose")
        self.chain = DECOMPOSE_PROMPT | llm | _PARSER

    async def run(self, state: PlanningState) -> PlanningState:
        """执行组件分解节点逻辑。"""
        ar = state["analysis_result"]
        reqs = ar.requirements[:10] if hasattr(ar, "requirements") else []
        reqs_text = "\n".join(f"- {r.id}: {r.description[:100]}" for r in reqs)

        try:
            result: ComponentDecomposeResult = await self.chain.ainvoke({
                "pattern": state.get("selected_pattern", "分层架构"),
                "reqs": reqs_text or "无需求数据",
                "format_instructions": _PARSER.get_format_instructions(),
            })
            components = [
                ComponentDetail(
                    name=c.name,
                    type=cast(Literal["service", "module", "library"], c.type),
                    responsibility=c.responsibility,
                    key_functions=c.key_functions,
                    dependencies=c.dependencies,
                )
                for c in result.components
            ]
        except Exception:
            components = []

        return {**state, "component_decomposition": components}
