"""StakeholderAnalyzerNode — ⭐ 干系人分析。"""

from __future__ import annotations

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async

STAKEHOLDER_PROMPT = """你是一个项目经理。从以下 PRD 内容中提取干系人及其关注点。

返回 JSON 数组：
[
  {{
    "name": "系统管理员",
    "role": "运维",
    "concerns": ["系统可维护性", "日志监控"],
    "influence": "high"
  }}
]

PRD 内容：
{text}
"""


class StakeholderAnalyzerNode:
    """干系人分析节点：提取干系人及其关注点。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行干系人分析。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        prd_text = state["prd_raw"][:4000]
        prompt = STAKEHOLDER_PROMPT.format(text=prd_text)
        await call_llm_async(prompt, model="deepseek-v3")

        # 干系人信息存储到 state 中供 ResultAssembler 使用
        return state
