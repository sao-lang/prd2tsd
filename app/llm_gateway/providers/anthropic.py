"""Anthropic Messages API 协议适配器。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from app.llm_gateway.providers.base import BaseProvider
from contracts.models import ModelConfig


class AnthropicProvider(BaseProvider):
    """Anthropic Messages API 的真实协议适配器。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化复用连接池的异步 HTTP 客户端。"""
        super().__init__(config)
        base_url = config.base_url.rstrip("/") or "https://api.anthropic.com/v1"
        self._messages_path = "/messages" if base_url.endswith("/v1") else "/v1/messages"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=config.timeout,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": str(config.config.get("anthropic_version", "2023-06-01")),
                "content-type": "application/json",
            },
        )

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 Messages API 生成文本。"""
        model_name = model or self.config.default_model
        payload: dict[str, Any] = {
            "model": model_name,
            "max_tokens": kwargs.pop("max_tokens", 4096),
            "messages": [{"role": "user", "content": prompt}],
            **kwargs,
        }
        response = await self._client.post(self._messages_path, json=payload)
        response.raise_for_status()
        data = response.json()
        content = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=model_name,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )

    async def stream_complete(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """通过 Messages SSE 流输出文本增量。"""
        payload: dict[str, Any] = {
            "model": model or self.config.default_model,
            "max_tokens": kwargs.pop("max_tokens", 4096),
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            **kwargs,
        }
        async with self._client.stream("POST", self._messages_path, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                event = json.loads(raw)
                delta = event.get("delta", {})
                if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        yield str(text)

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """Anthropic Messages API 不提供 Embedding 能力。"""
        raise NotImplementedError("Anthropic Messages API 不支持 Embedding")

    async def rerank(
        self,
        query: str,
        docs: list[str],
        model: str = "",
        **kwargs: Any,
    ) -> RerankResponse:
        """Anthropic Messages API 不提供 Rerank 能力。"""
        raise NotImplementedError("Anthropic Messages API 不支持 Rerank")
