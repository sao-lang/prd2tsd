"""条件路由函数 — 用于 StateGraph 的 conditional_edges。"""

from __future__ import annotations

from typing import Literal

from app.orchestrator.state import OrchestratorState

ReviewDecision = Literal["approved", "changes_needed", "pending"]


def needs_review(state: OrchestratorState) -> str:
    """判断是否需要人工审核。

    根据当前状态决定路由目标：
    - "review_needed" → 进入 HumanReview 节点
    - "skip_review"  → 跳过审核进入下一阶段

    Args:
        state: 当前 OrchestratorState。

    Returns:
        路由目标。
    """
    # 如果配置了自动跳过审核，或者用户角色是 admin，直接跳过
    auto_approve = state.get("tenant_context") and state["tenant_context"].settings.get("auto_approve", False)
    if auto_approve or state.get("user_role") == "admin":
        return "skip_review"

    # 默认需要人工审核
    return "review_needed"
