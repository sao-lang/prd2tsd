"""PatternRecommendNode — LLM 推荐 2-3 种架构模式。"""

from __future__ import annotations

import json
from typing import Any

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async
from contracts.interfaces import PatternEval

PATTERN_PROMPT = """你是一个软件架构师。基于以下项目需求，推荐 2-3 种适合的架构模式。

项目：{project}
领域：{domain}
需求数量：{req_count}

返回 JSON 数组：
[
  {{
    "pattern_name": "微服务架构",
    "match_score": 8.5,
    "strengths": ["独立部署", "技术多样性"],
    "weaknesses": ["分布式复杂性", "运维成本高"],
    "complexity": "high"
  }}
]

只返回 JSON，不要其他内容。
"""


class PatternRecommendNode:
    """架构模式推荐节点：LLM 推荐候选架构模式。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行架构模式推荐。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 architecture_patterns。
        """
        ar = state["analysis_result"]
        prompt = PATTERN_PROMPT.format(
            project=ar.project_name,
            domain=", ".join(ar.domain_tags),
            req_count=len(ar.requirements),
        )
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            import re
            json_match = re.search(r"\[.*?\]", response, re.DOTALL)
            if json_match:
                data: list[dict[str, Any]] = json.loads(json_match.group())
                patterns = [PatternEval(**item) for item in data]
            else:
                patterns = []
        except (json.JSONDecodeError, Exception):
            patterns = []

        return {
            **state,
            "architecture_patterns": patterns,
        }
