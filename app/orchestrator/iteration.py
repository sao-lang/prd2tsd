"""IterationDecider — 根据 Evaluation 评分决定后续路由。"""

from __future__ import annotations

from typing import Literal

from app.orchestrator.state import OrchestratorState

RouteDecision = Literal["accept", "replan", "regenerate", "human_intervention"]


class IterationDecider:
    """评估决策：根据评分决定后续路由。"""

    ROUTE_MAP: dict[str, str] = {
        "accept": "final_assembly",
        "replan": "planning",
        "regenerate": "generation",
        "human_intervention": "analysis_human_review",
    }

    def run(self, state: OrchestratorState) -> str:
        """根据 EvaluationReport 决定路由目标。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            路由目标节点名（对应 ROUTE_MAP 中的值）。
        """
        report = state.get("evaluation_report")
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 3)

        # 达到最大迭代次数 → 强制接受
        if iteration_count >= max_iterations:
            return self.ROUTE_MAP["accept"]

        if report is None:
            # 没有评测报告 → 重做生成
            # 注意：iteration_count 已在 EvaluationAdapter 中递增，此处不再重复加
            return self.ROUTE_MAP["regenerate"]

        # 兼容 dict 和 BaseModel 两种格式
        if isinstance(report, dict):
            overall_score = report.get("overall_score", 0.0)
            dimension_scores = report.get("dimension_scores", {})
            critical_issues = report.get("critical_issues", [])
        else:
            overall_score = getattr(report, "overall_score", 0.0)
            dimension_scores = getattr(report, "dimension_scores", {})
            critical_issues = getattr(report, "critical_issues", [])

        # 评分 >= 85 → 通过
        if overall_score >= 85:
            return self.ROUTE_MAP["accept"]

        # 评分 >= 70 → 根据维度决定
        if overall_score >= 70:
            consistency = dimension_scores.get("consistency", 100)
            feasibility = dimension_scores.get("feasibility", 100)

            if consistency < 70:
                return self.ROUTE_MAP["regenerate"]
            if feasibility < 70:
                return self.ROUTE_MAP["replan"]

            return self.ROUTE_MAP["accept"]

        # 评分 < 70 → 迭代重做（iteration_count 已在 EvaluationAdapter 中递增）
        if critical_issues:
            return self.ROUTE_MAP["human_intervention"]

        return self.ROUTE_MAP["replan"]
