"""FormatExporterNode — ⭐ 多格式导出（PDF / DOCX / HTML）。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState

VIBE_DEFER_BLOCK_E = "多格式导出依赖块 E 的文档管理系统，当前仅占位"


class FormatExporterNode:
    """多格式导出节点：Markdown / PDF / DOCX / HTML。

    Note:
        当前仅支持 Markdown 格式。PDF/DOCX/HTML 在块 E 中实现。
    """

    def run(self, state: GenerationState) -> GenerationState:
        """执行格式导出。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        # VIBE_DEFER(块 E): PDF/DOCX/HTML 导出
        return state
