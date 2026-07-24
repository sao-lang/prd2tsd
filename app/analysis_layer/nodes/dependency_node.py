"""DependencyAnalyzerNode — LLM 分析需求之间的依赖关系。"""

from __future__ import annotations

import json
from typing import Any

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async, extract_json_from_llm
from contracts.interfaces import DependencyGraph

DEPENDENCY_PROMPT = """你是一个架构师。分析以下需求之间的依赖关系。
用 JSON 格式返回依赖图：
{{
  "nodes": ["FR-001", "FR-002", ...],
  "edges": [["FR-001", "FR-002", "depends_on"], ...]
}}

relation 可以是: "depends_on" / "conflicts_with" / "refines" / "contains"

需求列表：
{reqs}
"""


class DependencyAnalyzerNode:
    """依赖分析节点：LLM 分析需求间的依赖关系。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行依赖分析。

        Args:
            state: 当前状态，含 extracted_requirements。

        Returns:
            更新后的状态，含 dependency_graph。
        """
        req_summary = "\n".join(
            f"{r.id}: {r.description[:100]}" for r in state["extracted_requirements"]
        )
        if not req_summary:
            return {**state, "dependency_graph": DependencyGraph()}

        prompt = DEPENDENCY_PROMPT.format(reqs=req_summary)
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            raw = extract_json_from_llm(response)
            data: dict[str, Any] = json.loads(raw)
            graph = DependencyGraph(
                nodes=data.get("nodes", []),
                edges=[tuple(e) for e in data.get("edges", [])],
            )
        except (json.JSONDecodeError, Exception):
            graph = DependencyGraph()

        return {
            **state,
            "dependency_graph": graph,
        }
