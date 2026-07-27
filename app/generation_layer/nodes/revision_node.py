"""RevisionNode — 修复一致性问题。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState

REVISION_PROMPT = """修复以下文档中的一致性问题。

不一致问题：
{issues}

文档内容：
{content}

请返回修复后的完整内容。
"""


class RevisionNode:
    """修订节点：修复一致性问题。"""

    async def run(self, state: GenerationState) -> GenerationState:
        """执行修订。

        读取 ConsistencyCheckerNode 发现的问题，调用 LLM 修复受影响的章节。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含修复后的 section_contents。
        """
        from app.generation_layer.tools import call_llm_async

        issues = state.get("consistency_issues", [])
        if not issues:
            return state

        contents = state.get("section_contents", {})
        if not contents:
            return state

        # 组装涉及不一致的章节内容
        affected_content = "\n\n---\n\n".join(
            f"### {k}\n{v[:1000]}" for k, v in contents.items()
        )

        prompt = REVISION_PROMPT.format(
            issues="\n".join(issues),
            content=affected_content,
        )
        response = await call_llm_async(prompt, model="gpt-4o-mini")

        if response and response.strip():
            # 将 LLM 修复后的内容合并到原有 section_contents，保留所有 key
            updated = dict(state.get("section_contents", {}))
            updated["_revision_fix"] = response
            return {
                **state,
                "section_contents": updated,
            }

        return state
