"""KnowledgeAugmentNode — 调用块 B Pipeline 检索相关知识。"""

from __future__ import annotations

from app.planning_layer.models import PlanningState
from app.planning_layer.tools import retrieve_knowledge


class KnowledgeAugmentNode:
    """知识增强节点：调用块 B 的 RetrievalPipeline。"""

    async def run(self, state: PlanningState) -> PlanningState:
        """执行知识检索。

        Args:
            state: 当前状态，含 analysis_result。

        Returns:
            更新后的状态，含 knowledge_context。
        """
        project_name = state["analysis_result"].project_name
        query = f"{project_name} 架构设计 技术栈"
        context = await retrieve_knowledge(query)

        return {
            **state,
            "knowledge_context": context,
        }
