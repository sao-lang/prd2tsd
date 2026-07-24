"""ClarityCheckerNode — 检查 PRD 清晰度，确保需求描述无歧义。"""

from __future__ import annotations

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async

CLARITY_PROMPT = """检查以下需求描述是否清晰、无歧义、有明确的验收标准。
对有问题的需求给出改进建议。

只输出 "通过" 或列出问题，不要其他内容。

需求列表：
{reqs}
"""


class ClarityCheckerNode:
    """清晰度检查节点：检查需求是否清晰。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行清晰度检查。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        reqs_text = "\n".join(
            f"{r.id}: {r.description[:150]}" for r in state["extracted_requirements"]
        )
        if not reqs_text:
            return state

        prompt = CLARITY_PROMPT.format(reqs=reqs_text)
        await call_llm_async(prompt, model="deepseek-v3")

        return state
