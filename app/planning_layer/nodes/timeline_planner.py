"""TimelinePlannerNode — ⭐ 时间线规划（甘特图 + 里程碑）。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import call_llm_async

TIMELINE_PROMPT = """你是一个项目管理专家。为以下项目生成时间线规划和里程碑。

项目：{project}
组件数：{comp_count}

输出格式：用文本描述各阶段（调研/开发/测试/部署）的时间安排
和关键里程碑。
"""


class TimelinePlannerNode:
    """时间线规划节点：甘特图 + 里程碑生成。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行时间线规划。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        ar = state["analysis_result"]
        prompt = TIMELINE_PROMPT.format(
            project=ar.project_name,
            comp_count=len(state.get("component_decomposition", [])),
        )
        await call_llm_async(prompt, model="deepseek-v3")
        return state
