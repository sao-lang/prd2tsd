"""TechStackSelectNode — LLM 按维度分批选择技术栈。"""

from __future__ import annotations

import json
from typing import Any

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async
from contracts.interfaces import TechChoiceDetail

TECH_STACK_PROMPT = """你是一个技术选型专家。为以下项目选择技术栈。

项目：{project}
架构模式：{pattern}
领域：{domain}

按维度返回 JSON 数组：
[
  {{
    "dimension": "backend_framework",
    "recommendation": "FastAPI",
    "reason": "异步高性能，Python 生态",
    "alternatives": [{{"name": "Spring Boot", "pros": "...", "cons": "..."}}],
    "risks": ["学习成本"]
  }}
]

维度包括：backend_framework, database_primary, cache, message_queue, frontend, testing, ci_cd, monitoring
"""


class TechStackSelectNode:
    """技术栈选型节点：LLM 按维度决策。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行技术栈选型。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 tech_stack_choices。
        """
        ar = state["analysis_result"]
        prompt = TECH_STACK_PROMPT.format(
            project=ar.project_name,
            pattern=state.get("selected_pattern", "未确定"),
            domain=", ".join(ar.domain_tags),
        )
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            import re
            json_match = re.search(r"\[.*?\]", response, re.DOTALL)
            if json_match:
                data: list[dict[str, Any]] = json.loads(json_match.group())
                choices = [TechChoiceDetail(**item) for item in data]
            else:
                choices = []
        except (json.JSONDecodeError, Exception):
            choices = []

        return {
            **state,
            "tech_stack_choices": choices,
        }
