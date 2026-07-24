"""PatternConfirmNode — 从候选模式中选择最优。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState


class PatternConfirmNode:
    """模式确认节点：选择评分最高的架构模式。"""

    def run(self, state: PlanningState) -> PlanningState:
        """选择最优架构模式。

        Args:
            state: 当前状态，含 architecture_patterns。

        Returns:
            更新后的状态，含 selected_pattern。
        """
        patterns = state.get("architecture_patterns", [])
        if not patterns:
            return {**state, "selected_pattern": "分层架构"}

        best = max(patterns, key=lambda p: p.match_score)
        return {
            **state,
            "selected_pattern": best.pattern_name,
        }
