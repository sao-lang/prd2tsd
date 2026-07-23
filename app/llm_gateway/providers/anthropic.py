"""Anthropic Claude Provider（预留）。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.llm_gateway.models import LLMResponse
from app.llm_gateway.providers.base import BaseProvider
from contracts.models import ModelConfig

logger = get_logger("prd2tsd.provider")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude Provider（预留）。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 AnthropicProvider。

        Args:
            config: 模型配置。
        """
        super().__init__(config)

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 Claude API（预留实现）。

        Args:
            prompt: 输入提示词。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            LLMResponse。
        """
        logger.warning("AnthropicProvider 为预留实现")
        return LLMResponse(content="[Anthropic 预留实现]", model=model or self.config.default_model)
