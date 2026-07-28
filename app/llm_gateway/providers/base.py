"""Provider 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from contracts.models import ModelConfig


class BaseProvider(ABC):
    """Provider 抽象基类。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 Provider。

        Args:
            config: 模型配置。
        """
        self.config = config

    @abstractmethod
    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 LLM 生成文本。子类必须实现。

        Args:
            prompt: 输入提示词。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            LLMResponse。
        """
        raise NotImplementedError

    @abstractmethod
    async def stream_complete(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """流式调用 LLM，逐 token 生成文本。子类必须实现。

        Args:
            prompt: 输入提示词。
            model: 模型名。
            **kwargs: 额外参数。

        Yields:
            文本块（逐 token 或逐 chunk）。
        """
        raise NotImplementedError
        # 兼容非流式：yield 一次完整结果
        # pylint: disable=unreachable
        yield ""

    @abstractmethod
    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """调用 Embedding 模型。子类必须实现。

        Args:
            texts: 文本列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。
        """
        raise NotImplementedError

    @abstractmethod
    async def rerank(self, query: str, docs: list[str], model: str = "", **kwargs: Any) -> RerankResponse:
        """调用 Rerank 模型。子类必须实现。

        Args:
            query: 查询。
            docs: 文档列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            RerankResponse。
        """
        raise NotImplementedError
