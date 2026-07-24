"""HumanReviewNode — 人工审核中断节点。

使用 LangGraph 的 interrupt 机制暂停流程等待人工反馈。
"""

from __future__ import annotations

from langgraph.types import interrupt

from app.orchestrator.state import OrchestratorState


class HumanReviewNode:
    """人工审核节点。

    在关键阶段暂停 Orchestrator 流程，
    等待人工确认或修改意见。
    """

    def __init__(self, stage: str) -> None:
        """初始化审核节点。

        Args:
            stage: 审核阶段标识（analysis / planning）。
        """
        self.stage = stage

    def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行人工审核。

        发送审核请求给外部，并通过 interrupt 暂停，
        等待 `POST /api/v1/review/{task_id}/{stage}` 恢复。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState（审核通过后继续）。
        """
        stage_descriptions = {
            "analysis": "分析结果审核",
            "planning": "架构方案审核",
        }

        # 构造审核上下文
        review_context = {
            "stage": self.stage,
            "task_id": state.get("task_id"),
            "description": stage_descriptions.get(self.stage, f"{self.stage} 审核"),
            "data": self._extract_review_data(state),
        }

        # 使用 interrupt 暂停等待人工反馈
        feedback = interrupt(review_context)

        # 根据反馈更新状态
        if feedback and isinstance(feedback, dict):
            decision = feedback.get("decision", "approved")
            comment = feedback.get("comment", "")

            if decision == "needs_changes":
                # 标记需要修改
                state["status"] = "paused"
                state["error_message"] = f"人工审核未通过 ({self.stage}): {comment}"
            else:
                # 审核通过
                state["status"] = "running"

        return state

    def _extract_review_data(self, state: OrchestratorState) -> dict:
        """提取当前阶段需要审核的数据。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            审核数据字典。
        """
        if self.stage == "analysis":
            return {
                "analysis_result": state.get("analysis_result"),
                "requirements_count": len(state.get("extracted_requirements", [])),
                "constraints_count": len(state.get("extracted_constraints", [])),
            }

        if self.stage == "planning":
            return {
                "planning_result": state.get("planning_result"),
                "components_count": len(state.get("component_decomposition", [])),
                "tech_choices_count": len(state.get("tech_stack_choices", [])),
            }

        return {}
