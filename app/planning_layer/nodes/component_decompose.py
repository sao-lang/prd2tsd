"""ComponentDecomposeNode — LLM 将需求映射为组件。"""

from __future__ import annotations

import json
from typing import Any

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async
from contracts.interfaces import ComponentDetail

DECOMPOSE_PROMPT = """你是一个软件架构师。将以下需求分解为系统组件。

架构模式：{pattern}
需求：
{reqs}

返回 JSON 数组：
[
  {{
    "name": "用户服务",
    "type": "service",
    "responsibility": "处理用户注册、登录、权限管理",
    "key_functions": ["用户注册", "JWT 签发"],
    "dependencies": ["数据库"]
  }}
]
"""


class ComponentDecomposeNode:
    """组件分解节点：需求 → 组件映射。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行组件分解。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 component_decomposition。
        """
        ar = state["analysis_result"]
        reqs_text = "\n".join(f"{r.id}: {r.description[:100]}" for r in ar.requirements[:10])
        prompt = DECOMPOSE_PROMPT.format(
            pattern=state.get("selected_pattern", "分层架构"),
            reqs=reqs_text,
        )
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            import re
            json_match = re.search(r"\[.*?\]", response, re.DOTALL)
            if json_match:
                data: list[dict[str, Any]] = json.loads(json_match.group())
                components = [ComponentDetail(**item) for item in data]
            else:
                components = []
        except (json.JSONDecodeError, Exception):
            components = []

        return {
            **state,
            "component_decomposition": components,
        }
