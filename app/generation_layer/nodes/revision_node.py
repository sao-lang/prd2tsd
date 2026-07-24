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

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        return state
