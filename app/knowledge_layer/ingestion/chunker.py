"""多粒度分块 — Sentence / Paragraph / Section 三级分块策略。"""

from __future__ import annotations

import re
import uuid

from app.core.logger import get_logger
from app.knowledge_layer.models import Chunk

logger = get_logger("prd2tsd.knowledge.chunker")


class MultiGranularityChunker:
    """多粒度分块器。

    支持三级分块：
    - sentence: 按句号/换行切分句子
    - paragraph: 按空行/段落切分
    - section: 按 Markdown 标题切分
    """

    def __init__(
        self,
        sentence_max_words: int = 50,
        paragraph_max_words: int = 500,
    ) -> None:
        """初始化分块器。

        Args:
            sentence_max_words: 句子级最大词数（超出则截断）。
            paragraph_max_words: 段落级最大词数（超出则截断）。
        """
        self.sentence_max_words = sentence_max_words
        self.paragraph_max_words = paragraph_max_words

    def chunk(
        self,
        text: str,
        level: str = "paragraph",
    ) -> list[Chunk]:
        """按指定粒度分块。

        Args:
            text: 输入文本。
            level: 分块粒度（sentence / paragraph / section）。

        Returns:
            分块列表。
        """
        if level == "sentence":
            return self._chunk_by_sentence(text)
        if level == "paragraph":
            return self._chunk_by_paragraph(text)
        if level == "section":
            return self._chunk_by_section(text)
        raise ValueError(f"不支持的分块粒度: {level}，可选: sentence, paragraph, section")

    def chunk_all_levels(self, text: str) -> dict[str, list[Chunk]]:
        """全部分块粒度同时切分。

        Args:
            text: 输入文本。

        Returns:
            {粒度: 分块列表} 字典。
        """
        return {
            "sentence": self._chunk_by_sentence(text),
            "paragraph": self._chunk_by_paragraph(text),
            "section": self._chunk_by_section(text),
        }

    def _chunk_by_sentence(self, text: str) -> list[Chunk]:
        """按句子分块。

        Args:
            text: 输入文本。

        Returns:
            句子级分块列表。
        """
        raw_sentences = re.split(r"(?<=[。！？\n])\s*", text)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        chunks: list[Chunk] = []
        for i, sent in enumerate(sentences):
            words = len(sent)
            if words > self.sentence_max_words:
                # 超长句子按逗号再切
                sub_parts = re.split(r"(?<=[，；])\s*", sent)
                for j, part in enumerate(sub_parts):
                    if part.strip():
                        chunks.append(
                            Chunk(
                                id=str(uuid.uuid4()),
                                text=part.strip(),
                                level="sentence",
                                index=i * 100 + j,
                            )
                        )
            else:
                chunks.append(
                    Chunk(
                        id=str(uuid.uuid4()),
                        text=sent,
                        level="sentence",
                        index=i,
                    )
                )
        logger.debug("句子级分块: %d chunks", len(chunks))
        return chunks

    def _chunk_by_paragraph(self, text: str) -> list[Chunk]:
        """按段落分块。

        Args:
            text: 输入文本。

        Returns:
            段落级分块列表。
        """
        paragraphs = re.split(r"\n\s*\n", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        chunks: list[Chunk] = []
        for i, para in enumerate(paragraphs):
            words = len(para)
            if words > self.paragraph_max_words:
                # 超长段落按句号截断
                sub_sentences = re.split(r"(?<=[。！？])\s*", para)
                buffer = ""
                for sent in sub_sentences:
                    if len(buffer) + len(sent) < self.paragraph_max_words:
                        buffer += sent
                    else:
                        if buffer.strip():
                            chunks.append(
                                Chunk(
                                    id=str(uuid.uuid4()),
                                    text=buffer.strip(),
                                    level="paragraph",
                                    index=len(chunks),
                                )
                            )
                        buffer = sent
                if buffer.strip():
                    chunks.append(
                        Chunk(
                            id=str(uuid.uuid4()),
                            text=buffer.strip(),
                            level="paragraph",
                            index=len(chunks),
                        )
                    )
            else:
                chunks.append(
                    Chunk(
                        id=str(uuid.uuid4()),
                        text=para,
                        level="paragraph",
                        index=i,
                    )
                )
        logger.debug("段落级分块: %d chunks", len(chunks))
        return chunks

    def _chunk_by_section(self, text: str) -> list[Chunk]:
        """按 Markdown 标题分块。

        Args:
            text: 输入文本。

        Returns:
            章节级分块列表。
        """
        # 匹配 ## 级别标题（含 #, ##, ###）
        pattern = r"^(#{1,3})\s+(.+)$"
        lines = text.split("\n")
        sections: list[tuple[str, str, list[str]]] = []  # (level, title, content_lines)
        current_level = ""
        current_title = ""
        current_lines: list[str] = []

        for line in lines:
            match = re.match(pattern, line)
            if match:
                if current_lines:
                    sections.append((current_level, current_title, current_lines))
                current_level = match.group(1)
                current_title = match.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((current_level, current_title, current_lines))

        chunks: list[Chunk] = []
        for i, (level, title, content_lines) in enumerate(sections):
            text_content = "\n".join(content_lines).strip()
            if not text_content:
                continue
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    text=text_content,
                    level="section",
                    section_path=f"{level} {title}",
                    index=i,
                )
            )
        logger.debug("章节级分块: %d chunks", len(chunks))
        return chunks
