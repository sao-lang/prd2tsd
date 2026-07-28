"""C1 — Analysis Layer 工具函数。

Phase 6 清理：call_llm_async / extract_json_from_llm 已删除，
所有节点已迁移到 LangChain ChatPromptTemplate + PydanticOutputParser。
"""

from __future__ import annotations

import re

from contracts.interfaces import DocumentSection


def parse_markdown_sections(text: str) -> list[DocumentSection]:
    """将 Markdown 文本按标题拆分为结构化章节。

    Args:
        text: 原始 Markdown 文本。

    Returns:
        章节列表（含层级关系）。
    """
    lines = text.splitlines()
    sections: list[DocumentSection] = []
    stack: list[tuple[int, DocumentSection]] = []  # (level, section)

    for line in lines:
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            new_sec = DocumentSection(title=title, level=level, content="")

            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].subsections.append(new_sec)

            stack.append((level, new_sec))
            sections.append(new_sec)
        elif sections:
            sections[-1].content += line + "\n"

    return sections
