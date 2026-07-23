"""LLM 客户端 — 基于 OpenAI SDK，兼容 DeepSeek API 格式。"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings


def create_llm_client(
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: int = 60,
    max_retries: int = 3,
) -> AsyncOpenAI:
    """创建 OpenAI 兼容的异步 LLM 客户端。

    Args:
        api_key: API 密钥。为 None 时从配置读取。
        base_url: API 端点。为 None 时从配置读取。
        timeout: 超时秒数。
        max_retries: 最大重试次数。

    Returns:
        配置好的 AsyncOpenAI 客户端。
    """
    return AsyncOpenAI(
        api_key=api_key or settings.MODEL_CONFIG__LLM__DEEPSEEK__API_KEY or "",
        base_url=base_url or settings.MODEL_CONFIG__LLM__DEEPSEEK__BASE_URL,
        timeout=timeout,
        max_retries=max_retries,
    )


async def llm_complete(
    prompt: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> str:
    """调用 LLM 生成文本。

    Args:
        prompt: 输入提示词。
        model: 模型名。为 None 时使用配置的默认模型。
        api_key: API 密钥。为 None 时从配置读取。
        base_url: API 端点。为 None 时从配置读取。
        temperature: 温度参数。
        max_tokens: 最大生成 Token 数。
        **kwargs: 额外参数传递给 OpenAI API。

    Returns:
        生成的文本内容。

    Raises:
        Exception: API 调用失败时抛出。
    """
    client = create_llm_client(api_key=api_key, base_url=base_url)
    response = await client.chat.completions.create(
        model=model or settings.MODEL_CONFIG__LLM__DEEPSEEK__DEFAULT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    return response.choices[0].message.content or ""
