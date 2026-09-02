"""Cohere V2 API 协议适配器。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from app.llm_gateway.providers.base import BaseProvider
from contracts.models import ModelConfig


class CohereProvider(BaseProvider):
    """Cohere V2 Chat、Embed 与 Rerank 真实协议适配器。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化复用连接池的异步 HTTP 客户端。"""
        super().__init__(config)
        base_url = config.base_url.rstrip("/") or "https://api.cohere.com/v2"
        self._api_prefix = "" if base_url.endswith("/v2") else "/v2"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=config.timeout,
            headers={"authorization": f"Bearer {config.api_key}", "content-type": "application/json"},
        )

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 Cohere V2 Chat。"""
        model_name = model or self.config.default_model
        response = await self._client.post(
            f"{self._api_prefix}/chat",
            json={"model": model_name, "messages": [{"role": "user", "content": prompt}], **kwargs},
        )
        response.raise_for_status()
        data = response.json()
        blocks = data.get("message", {}).get("content", [])
        content = "".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict))
        billed = data.get("usage", {}).get("billed_units", {})
        return LLMResponse(
            content=content,
            model=model_name,
            input_tokens=int(billed.get("input_tokens", 0)),
            output_tokens=int(billed.get("output_tokens", 0)),
        )

    async def stream_complete(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """调用 Cohere V2 Chat SSE。"""
        payload = {
            "model": model or self.config.default_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            **kwargs,
        }
        async with self._client.stream("POST", f"{self._api_prefix}/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                event = json.loads(raw)
                if event.get("type") != "content-delta":
                    continue
                text = event.get("delta", {}).get("message", {}).get("content", {}).get("text", "")
                if text:
                    yield str(text)

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """调用 Cohere V2 Embed，默认返回 1024 维 float 向量。"""
        model_name = model or self.config.default_model
        payload = {
            "model": model_name,
            "texts": texts,
            "input_type": kwargs.pop("input_type", "search_document"),
            "embedding_types": ["float"],
            "output_dimension": kwargs.pop("output_dimension", 1024),
            **kwargs,
        }
        response = await self._client.post(f"{self._api_prefix}/embed", json=payload)
        response.raise_for_status()
        data = response.json()
        billed = data.get("meta", {}).get("billed_units", {})
        return EmbeddingResponse(
            embeddings=data.get("embeddings", {}).get("float", []),
            model=model_name,
            input_tokens=int(billed.get("input_tokens", 0)),
        )

    async def rerank(
        self,
        query: str,
        docs: list[str],
        model: str = "",
        **kwargs: Any,
    ) -> RerankResponse:
        """调用 Cohere V2 Rerank。"""
        model_name = model or self.config.default_model
        payload = {
            "model": model_name,
            "query": query,
            "documents": docs,
            "top_n": kwargs.pop("top_n", len(docs)),
            **kwargs,
        }
        response = await self._client.post(f"{self._api_prefix}/rerank", json=payload)
        response.raise_for_status()
        results = response.json().get("results", [])
        return RerankResponse(
            scores=[float(item["relevance_score"]) for item in results],
            indices=[int(item["index"]) for item in results],
            model=model_name,
            input_tokens=(len(query) + sum(len(doc) for doc in docs)) // 4,
        )
