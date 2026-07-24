"""RequirementQualityNode — ⭐ 需求质量 6 维评分。"""

from __future__ import annotations

import json
from typing import Any

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async, extract_json_from_llm

QUALITY_PROMPT = """你是一个需求质量评审专家。对以下需求列表进行 6 维评分（每维 0-10 分）。

评分维度：
1. completeness（完整性）：是否涵盖了所有必要方面
2. clarity（清晰度）：描述是否清晰无歧义
3. testability（可测试性）：是否可验证
4. consistency（一致性）：是否存在内部矛盾
5. necessity（必要性）：是否真正必要
6. feasibility（可行性）：在技术上是否可行

返回 JSON：
{{
  "dimensions": {{
    "completeness": 8,
    "clarity": 7,
    ...
  }},
  "overall": 7.5,
  "suggestions": ["改进建议..."]
}}

需求列表：
{reqs}
"""


class RequirementQualityNode:
    """需求质量评分节点：6 维评分。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行质量评分。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，quality 信息存入 confidence。
        """
        reqs_text = "\n".join(
            f"{r.id} [{r.priority}] {r.description[:100]}" for r in state["extracted_requirements"]
        )
        if not reqs_text:
            return {**state, "confidence": 0.0}

        prompt = QUALITY_PROMPT.format(reqs=reqs_text)
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            raw = extract_json_from_llm(response)
            data: dict[str, Any] = json.loads(raw)
            overall = float(data.get("overall", 0)) / 10.0
        except (json.JSONDecodeError, Exception):
            overall = 0.5

        return {
            **state,
            "confidence": overall,
        }
