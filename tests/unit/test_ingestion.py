"""单元测试 — 文档加载和分块。"""

from __future__ import annotations

import pytest

from app.knowledge_layer.ingestion.chunker import MultiGranularityChunker
from app.knowledge_layer.ingestion.document_loader import DocumentLoader


class TestDocumentLoader:
    """文档加载器测试。"""

    def test_load_markdown(self, tmp_path) -> None:
        """验证加载 .md 文件。"""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello\nWorld", encoding="utf-8")
        loader = DocumentLoader()
        text = loader.load(str(md_file))
        assert "# Hello" in text
        assert "World" in text

    def test_load_nonexistent_file(self) -> None:
        """验证不存在的文件抛出异常。"""
        loader = DocumentLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("/nonexistent/file.md")

    def test_unsupported_format(self, tmp_path) -> None:
        """验证不支持的文件格式抛出异常。"""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello", encoding="utf-8")
        loader = DocumentLoader()
        with pytest.raises(ValueError, match="不支持的文件格式"):
            loader.load(str(txt_file))


class TestMultiGranularityChunker:
    """多粒度分块器测试。"""

    SAMPLE_TEXT = """# 用户服务

用户服务使用 Spring Boot 框架。

## 技术栈

使用 PostgreSQL 数据库。使用 Redis 缓存。

## 部署

使用 Docker 部署。使用 Kubernetes 编排。"""

    def test_chunk_by_sentence(self) -> None:
        """验证句子级分块。"""
        chunker = MultiGranularityChunker()
        chunks = chunker.chunk(self.SAMPLE_TEXT, level="sentence")
        assert len(chunks) >= 3
        assert all(c.level == "sentence" for c in chunks)
        assert all(c.text for c in chunks)

    def test_chunk_by_paragraph(self) -> None:
        """验证段落级分块。"""
        chunker = MultiGranularityChunker()
        chunks = chunker.chunk(self.SAMPLE_TEXT, level="paragraph")
        assert len(chunks) >= 3
        assert all(c.level == "paragraph" for c in chunks)

    def test_chunk_by_section(self) -> None:
        """验证章节级分块。"""
        chunker = MultiGranularityChunker()
        chunks = chunker.chunk(self.SAMPLE_TEXT, level="section")
        assert len(chunks) >= 3
        assert all(c.level == "section" for c in chunks)

    def test_chunk_all_levels(self) -> None:
        """验证全部分块粒度。"""
        chunker = MultiGranularityChunker()
        result = chunker.chunk_all_levels(self.SAMPLE_TEXT)
        assert "sentence" in result
        assert "paragraph" in result
        assert "section" in result

    def test_invalid_level(self) -> None:
        """验证无效分块粒度。"""
        chunker = MultiGranularityChunker()
        with pytest.raises(ValueError, match="不支持的分块粒度"):
            chunker.chunk("text", level="invalid")

    def test_empty_text(self) -> None:
        """验证空文本分块。"""
        chunker = MultiGranularityChunker()
        chunks = chunker.chunk("", level="paragraph")
        assert len(chunks) == 0
