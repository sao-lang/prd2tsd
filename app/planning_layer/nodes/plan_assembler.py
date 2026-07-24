"""PlanAssemblerNode — 组装最终 PlanningResult。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from contracts.interfaces import PlanningResultDetail


class PlanAssemblerNode:
    """规划结果组装节点。"""

    def run(self, state: PlanningState) -> PlanningState:
        """组装规划结果。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 planning_result。
        """
        result = PlanningResultDetail(
            architecture_pattern=state.get("selected_pattern", "分层架构"),
            tech_stack=state.get("tech_stack_choices", []),
            components=state.get("component_decomposition", []),
            component_diagram=self._build_mermaid(state),
        )

        return {
            **state,
            "planning_result": result,
        }

    @staticmethod
    def _build_mermaid(state: PlanningState) -> str:
        """生成组件关系 Mermaid 图。

        Args:
            state: 当前状态。

        Returns:
            Mermaid 代码。
        """
        comps = state.get("component_decomposition", [])
        if not comps:
            return "graph TD\n  A[待规划]"

        lines = ["graph TD"]
        for i, c in enumerate(comps):
            node_id = f"C{i}"
            lines.append(f"  {node_id}[{c.name}]")
            for dep in c.dependencies:
                dep_idx = next((j for j, x in enumerate(comps) if x.name == dep), None)
                if dep_idx is not None:
                    lines.append(f"  C{dep_idx} --> {node_id}")
                else:
                    lines.append(f"  EXT[{dep}] -.-> {node_id}")

        return "\n".join(lines)
