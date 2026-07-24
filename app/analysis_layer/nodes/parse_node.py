"""DocumentParserNode — 将 PRD 按 Markdown 标题拆分为结构化章节。"""

from __future__ import annotations

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import parse_markdown_sections


class DocumentParserNode:
    """文档解析节点：按 Markdown 标题层级拆分为结构化章节。"""

    def run(self, state: AnalysisState) -> AnalysisState:
        """执行文档解析。

        Args:
            state: 当前状态，含 prd_raw。

        Returns:
            更新后的状态，含 prd_sections。
        """
        sections = parse_markdown_sections(state["prd_raw"])
        return {
            **state,
            "prd_sections": sections,
        }
