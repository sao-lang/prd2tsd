"""RevisionNode — LangChain 修复一致性问题。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.generation_layer.models import GenerationState
from app.llm_gateway.langchain_adapter import GatewayChatModel

REVISION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "修复以下文档中的一致性问题。请返回修复后的完整内容。"),
    ("human", "不一致问题：\n{issues}\n\n文档内容：\n{content}"),
])


class RevisionNode:
    """修订节点：LangChain 链修复一致性问题。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="generation", layer="generation", node="revision")
        self.chain = REVISION_PROMPT | llm

    async def run(self, state: GenerationState) -> GenerationState:
        """执行一致性修订节点逻辑。"""
        issues_raw = state.get("consistency_issues", [])
        issues = issues_raw if isinstance(issues_raw, list) else [issues_raw]
        if not issues:
            return state

        contents = state.get("section_contents", {})
        if not contents:
            return state

        affected_content = "\n\n---\n\n".join(f"### {k}\n{v[:1000]}" for k, v in contents.items())

        result = await self.chain.ainvoke({
            "issues": "\n".join(issues),
            "content": affected_content,
        })
        response = (
            result.content
            if isinstance(result.content, str)
            else str(result)
        )

        if response and response.strip():
            updated = dict(state.get("section_contents", {}))
            updated["_revision_fix"] = response
            return {**state, "section_contents": updated}

        return state
