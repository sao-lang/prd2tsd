"""知识层接口定义 — 可替换组件的 Protocol 边界。

在当前自实现和未来 LlamaIndex 实现之间画一条清晰的 Protocol 边界。
当项目条件成熟（文档格式 >6 种 / 检索需要 A/B 实验 / 多模态需求），
可以无痛切换到 LlamaIndex 实现。当前不做任何切换，只做接口抽离。

三层架构：
- 不可替换层（永远保留）：GlobalSearch / ReflectionJudge / EntityResolver 等
- 接口层（Protocol）：DocumentReader / TextChunker / TextEmbedder 等
- 当前实现层（自实现）：LocalDocumentLoader / MultiGranularityChunker 等
"""

from __future__ import annotations

from typing import Any, Protocol


class DocumentReader(Protocol):
    """文档读取器接口 — 从文件路径加载文档。"""

    async def load(self, file_path: str) -> list[Any]:
        """加载文档。

        Args:
            file_path: 文件路径。

        Returns:
            文档对象列表。
        """
        ...


class TextChunker(Protocol):
    """文本分块器接口 — 将文本切分为语义块。"""

    def chunk(self, text: str) -> list[Any]:
        """切分文本。

        Args:
            text: 原始文本。

        Returns:
            文本块列表。
        """
        ...


class TextEmbedder(Protocol):
    """文本嵌入器接口 — 将文本转为向量。"""

    async def embed(self, text: str) -> list[float]:
        """文本嵌入。

        Args:
            text: 输入文本。

        Returns:
            向量表示。
        """
        ...


class QueryRewriterInterface(Protocol):
    """查询重写器接口 — 优化用户查询以提高检索精度。"""

    async def rewrite(self, query: str) -> str:
        """重写查询。

        Args:
            query: 原始查询。

        Returns:
            优化后的查询。
        """
        ...


class ResultFuser(Protocol):
    """结果融合器接口 — 合并多个检索排名列表。"""

    def fuse(self, rankings: list[list[Any]]) -> list[Any]:
        """融合多个排名列表。

        Args:
            rankings: 多个检索排名列表。

        Returns:
            融合后的排序结果。
        """
        ...


class ResultReranker(Protocol):
    """结果重排器接口 — 对检索结果二次精排。"""

    async def rerank(self, query: str, docs: list[Any]) -> list[Any]:
        """重排检索结果。

        Args:
            query: 查询文本。
            docs: 候选文档列表。

        Returns:
            重排后的文档列表。
        """
        ...
