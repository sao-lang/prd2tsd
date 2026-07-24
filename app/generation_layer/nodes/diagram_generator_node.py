"""DiagramGeneratorNode — 生成 Mermaid 架构图。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState


class DiagramGeneratorNode:
    """Mermaid 图表生成节点。"""

    def run(self, state: GenerationState) -> GenerationState:
        """生成 Mermaid 架构图。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 generation_result 中的 mermaid_diagrams。
        """
        pr = state["planning_result"]
        mermaid: dict[str, str] = {}

        if pr.component_diagram:
            mermaid["architecture"] = pr.component_diagram

        return state
