"""OpenAI 兼容 Provider — 兼容 OpenAI / DeepSeek / Azure OpenAI。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from app.core.logger import get_logger
from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from app.llm_gateway.providers.base import BaseProvider
from contracts.models import ModelConfig

logger = get_logger("prd2tsd.provider")


class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 Provider — 兼容 OpenAI / DeepSeek / Azure OpenAI。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 OpenAIProvider。

        Args:
            config: 模型配置（含 api_key, base_url 等）。
        """
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 OpenAI 兼容的 Chat Completion API。

        Block F 增强：
        - tools / tool_choice：Function Calling 支持
        - response_format：结构化输出（JSON Schema 约束）
        - stream + event_queue：流式逐 token 输出

        Args:
            prompt: 输入提示词。
            model: 模型名。为空时使用配置的默认模型。
            **kwargs: 额外参数（temperature, max_tokens, tools, tool_choice,
                      response_format, stream, event_queue 等）。

        Returns:
            LLMResponse。
        """
        model_name = model or self.config.default_model
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 4096)
        stream = kwargs.pop("stream", False)
        event_queue = kwargs.pop("event_queue", None)
        images = kwargs.pop("images", None)
        user_content: Any = prompt
        if images:
            content_blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            for image in images:
                image_url = image if isinstance(image, dict) else {"url": str(image)}
                content_blocks.append({"type": "image_url", "image_url": image_url})
            user_content = content_blocks

        params: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Block F: tools / tool_choice / response_format 透传
        tools = kwargs.pop("tools", None)
        tool_choice = kwargs.pop("tool_choice", None)
        response_format = kwargs.pop("response_format", None)
        if tools:
            params["tools"] = tools
        if tool_choice:
            params["tool_choice"] = tool_choice
        if response_format:
            params["response_format"] = response_format

        # Block F: 流式支持
        if stream:
            return await self._complete_stream(
                model_name=model_name,
                params=params,
                event_queue=event_queue,
            )

        # 非流式调用
        params.update(kwargs)
        response = await self._client.chat.completions.create(**params)

        choice = response.choices[0]
        usage = response.usage

        # Block F: 提取 tool_calls
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in choice.message.tool_calls
            ]

        return LLMResponse(
            content=choice.message.content or "",
            model=model_name,
            cost=self._calculate_cost(usage.prompt_tokens, usage.completion_tokens, model_name),
            input_tokens=usage.prompt_tokens or 0,
            output_tokens=usage.completion_tokens or 0,
            metadata={"tool_calls": tool_calls} if tool_calls else {},
        )

    async def _complete_stream(
        self,
        model_name: str,
        params: dict[str, Any],
        event_queue: Any = None,
    ) -> LLMResponse:
        """流式调用 LLM，逐 token 推入 event_queue。"""
        response = await self._client.chat.completions.create(**{**params, "stream": True})

        full_content = ""
        token_index = 0
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta and event_queue:
                await event_queue.put(
                    {
                        "event": "token",
                        "data": {"text": delta, "index": token_index},
                    }
                )
                token_index += 1
            full_content += delta

        if event_queue:
            await event_queue.put(
                {
                    "event": "token_done",
                    "data": {"total_tokens": token_index},
                }
            )

        return LLMResponse(
            content=full_content,
            model=model_name,
            cost=0.0,
            input_tokens=0,
            output_tokens=token_index,
        )

    async def stream_complete(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """流式调用 LLM，逐 token 生成文本。

        Args:
            prompt: 输入提示词。
            model: 模型名。为空时使用配置的默认模型。
            **kwargs: 额外参数（temperature, max_tokens 等）。

        Yields:
            文本块（逐 token）。
        """
        model_name = model or self.config.default_model
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 4096)
        images = kwargs.pop("images", None)
        user_content: Any = prompt
        if images:
            content_blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            for image in images:
                image_url = image if isinstance(image, dict) else {"url": str(image)}
                content_blocks.append({"type": "image_url", "image_url": image_url})
            user_content = content_blocks

        params: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }

        response = await self._client.chat.completions.create(**params)

        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """调用 OpenAI 兼容的 Embedding API。

        Args:
            texts: 文本列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。
        """
        model_name = model or self.config.default_model
        response = await self._client.embeddings.create(
            model=model_name,
            input=texts,
            **kwargs,
        )

        embeddings = [item.embedding for item in response.data]
        usage = response.usage

        return EmbeddingResponse(
            embeddings=embeddings,
            model=model_name,
            input_tokens=usage.prompt_tokens or 0,
            cost=self._calculate_cost(usage.prompt_tokens, 0, model_name),
        )

    async def rerank(self, query: str, docs: list[str], model: str = "", **kwargs: Any) -> RerankResponse:
        """OpenAI Provider 暂不支持 Rerank，通过模拟返回。

        Args:
            query: 查询。
            docs: 文档列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            RerankResponse（模拟）。
        """
        logger.warning("OpenAIProvider.rerank 为模拟实现，返回等权重排序")
        n = len(docs)
        scores = [1.0 - i * 0.1 for i in range(n)]
        indices = list(range(n))
        return RerankResponse(
            scores=scores,
            indices=indices,
            model=model or self.config.default_model,
            input_tokens=len(query) + sum(len(d) for d in docs),
        )

    @staticmethod
    def _calculate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """估算调用成本。

        Args:
            prompt_tokens: 输入 Token 数。
            completion_tokens: 输出 Token 数。
            model: 模型名。

        Returns:
            估算成本（美元）。
        """
        from app.llm_gateway.pricing import estimate_cost

        return estimate_cost(model, prompt_tokens, completion_tokens)
