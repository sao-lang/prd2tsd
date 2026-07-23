"""文档加载 — 支持 .md 文件的多格式加载和解析。"""

from __future__ import annotations

from pathlib import Path

from app.core.logger import get_logger

logger = get_logger("prd2tsd.knowledge.document_loader")


class DocumentLoader:
    """多格式文档加载器（先只做 .md）。"""

    SUPPORTED_EXTENSIONS = {".md"}

    def load(self, file_path: str) -> str:
        """加载文档内容。

        Args:
            file_path: 文件路径。

        Returns:
            文档文本内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            ValueError: 不支持的文件格式时抛出。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {path.suffix}，仅支持: {self.SUPPORTED_EXTENSIONS}")

        text = path.read_text(encoding="utf-8")
        logger.info("文档已加载: %s (%d chars)", file_path, len(text))
        return text
