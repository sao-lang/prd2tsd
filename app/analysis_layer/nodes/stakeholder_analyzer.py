"""StakeholderAnalyzerNode — ⭐ 干系人分析。"""

from __future__ import annotations

import json
from typing import Any

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async, extract_json_from_llm

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
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            raw = extract_json_from_llm(response)
            stakeholders: list[dict[str, Any]] = json.loads(raw)
            if not isinstance(stakeholders, list):
                stakeholders = [stakeholders]
        except (json.JSONDecodeError, Exception):
            stakeholders = []

        return {**state, "stakeholders": stakeholders}
