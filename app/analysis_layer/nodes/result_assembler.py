"""AnalysisResultAssemblerNode — 组装最终 AnalysisResult。"""

from __future__ import annotations

from app.analysis_layer.models import AnalysisState
from contracts.interfaces import AnalysisResultDetail, DependencyGraph


class AnalysisResultAssemblerNode:
    """结果组装节点：将各节点输出组装为 AnalysisResultDetail。"""

    def run(self, state: AnalysisState) -> AnalysisState:
        """组装分析结果。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 analysis_result。
        """
        # 从 PRD 首行提取项目名
        first_line = state["prd_raw"].strip().splitlines()[0] if state["prd_raw"] else ""
        project_name = first_line.lstrip("#").strip() if first_line else "未知项目"

        result = AnalysisResultDetail(
            project_name=project_name,
            summary=state["prd_raw"][:200].replace("\n", " ").strip(),
            domain_tags=state.get("domain_tags", []),
            requirements=state.get("extracted_requirements", []),
            constraints=state.get("extracted_constraints", []),
            dependency_graph=state.get("dependency_graph", DependencyGraph()),
            confidence=state.get("confidence", 0.0),
        )

        return {
            **state,
            "analysis_result": result,
        }
