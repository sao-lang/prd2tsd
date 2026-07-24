"""DeploymentPlanningNode — 部署方案草稿。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

DEPLOY_PROMPT = """为以下项目设计部署方案。

项目：{project}
架构模式：{pattern}

说明容器化方案、CI/CD 流程、环境规划等。
"""


class DeploymentPlanningNode:
    """部署方案规划节点。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行部署方案规划。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        ar = state["analysis_result"]
        prompt = DEPLOY_PROMPT.format(
            project=ar.project_name,
            pattern=state.get("selected_pattern", "分层架构"),
        )
        await call_llm_async(prompt, model="deepseek-v3")
        return state
