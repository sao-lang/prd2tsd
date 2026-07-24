"""FormatAssemblerNode — 组装为完整 Markdown 文档。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState
from contracts.interfaces import GenerationResultDetail


class FormatAssemblerNode:
    """格式组装节点：组装为完整 Markdown。"""

    def run(self, state: GenerationState) -> GenerationState:
        """组装 Markdown 文档。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 generation_result。
        """
        outline = state.get("outline", [])
        contents = state.get("section_contents", {})

        # 按大纲顺序组装
        lines: list[str] = []
        for sec in outline:
            if sec.section_id in contents:
                lines.append(contents[sec.section_id])
                lines.append("")

        content = "\n".join(lines) if lines else "# 技术方案文档\n\n（内容待生成）"

        result = GenerationResultDetail(
            content=content,
            sections=contents,
            mermaid_diagrams={},
        )

        return {
            **state,
            "generation_result": result,
        }
