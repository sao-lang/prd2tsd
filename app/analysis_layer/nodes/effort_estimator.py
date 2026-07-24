"""EffortEstimatorNode — ⭐ COCOMO II + LLM 工作量估算。"""

from __future__ import annotations

import json
from typing import Any

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async, extract_json_from_llm

EFFORT_PROMPT = """你是一个软件估算专家。基于以下需求列表进行工作量估算。

请评估：
1. 代码行数估算（KSLOC）
2. 人员月数（Person-Months）
3. 建议团队规模
4. 估算置信度（0-1）

按 COCOMO II 基本模型（organic/semi-detached/embedded）估算。

返回 JSON 格式：
{{
  "ksloc": 10.5,
  "person_months": 6.0,
  "team_size": 4,
  "model_type": "semi-detached",
  "confidence": 0.7,
  "description": "估算说明"
}}

需求列表：
{reqs}
"""


class EffortEstimatorNode:
    """工作量估算节点：COCOMO II + LLM 调整。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行工作量估算。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态（confidence 融合估算置信度）。
        """
        reqs_text = "\n".join(
            f"{r.id} [{r.priority}] {r.category}: {r.description[:120]}"
            for r in state["extracted_requirements"]
        )
        if not reqs_text:
            return state

        prompt = EFFORT_PROMPT.format(reqs=reqs_text)
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            raw = extract_json_from_llm(response)
            data: dict[str, Any] = json.loads(raw)
            effort_conf = float(data.get("confidence", 0.5))
            merged_conf = (state["confidence"] + effort_conf) / 2.0
        except (json.JSONDecodeError, Exception):
            merged_conf = state["confidence"]

        return {
            **state,
            "confidence": merged_conf,
        }
