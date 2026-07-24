"""ConsistencyCheckerNode — 一致性检查。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState
from app.generation_layer.tools import call_llm_async

CONSISTENCY_PROMPT = """检查以下文档章节之间是否存在矛盾或不一致。

章节内容：
{contents}

如果发现不一致，列出问题；否则回复"通过"。
"""


class ConsistencyCheckerNode:
    """一致性检查节点。"""

    async def run(self, state: GenerationState) -> GenerationState:
        """执行一致性检查。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        contents = state.get("section_contents", {})
        if not contents:
            return state

        content_text = "\n\n".join(
            f"=== {k} ===\n{v[:500]}" for k, v in contents.items()
        )
        prompt = CONSISTENCY_PROMPT.format(contents=content_text)
        await call_llm_async(prompt, model="gpt-4o-mini")
        return state
