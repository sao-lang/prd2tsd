"""ConsistencyCheckerNode — LangChain 一致性检查。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.generation_layer.models import GenerationState
from app.llm_gateway.langchain_adapter import GatewayChatModel

CONSISTENCY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "检查以下文档章节之间是否存在矛盾或不一致。如果发现不一致，列出问题；否则回复'通过'。"),
    ("human", "{contents}"),
])


class ConsistencyCheckerNode:
    """一致性检查节点：LangChain 链检测章节矛盾。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="generation", layer="generation", node="consistency_checker")
        self.chain = CONSISTENCY_PROMPT | llm

    async def run(self, state: GenerationState) -> GenerationState:
        """执行文档一致性检查节点逻辑。"""
        contents = state.get("section_contents", {})
        if not contents:
            return state

        content_text = "\n\n".join(f"=== {k} ===\n{v[:500]}" for k, v in contents.items())
        result = await self.chain.ainvoke({"contents": content_text})
        response = (
            result.content
            if isinstance(result.content, str)
            else str(result)
        )

        issues: list[str] = []
        if response and response.strip() not in ("", "通过"):
            issues = [line.strip() for line in response.split("\n") if line.strip()]
        return {**state, "consistency_issues": issues}
