"""LLM 客户端（已废弃）— 所有调用已迁移至 app.llm_gateway.gateway。

请使用 gateway.complete() 替代，它集成预算控制、速率限制、OpenTelemetry 追踪、
语义缓存和 Provider 路由。详见 app/llm_gateway/__init__.py。
"""

from __future__ import annotations

import warnings
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

warnings.warn(
    "app.core.llm 已废弃，请使用 app.llm_gateway.gateway.complete() 替代",
    DeprecationWarning,
    stacklevel=2,
)


def create_llm_client(
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: int = 60,
    max_retries: int = 3,
) -> AsyncOpenAI:
    """（已废弃）创建 OpenAI 兼容的异步 LLM 客户端。

    请改用 gateway.complete()，见 app.llm_gateway。
    """
    warnings.warn("create_llm_client 已废弃", DeprecationWarning, stacklevel=2)
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
    """（已废弃）调用 LLM 生成文本。

    请改用 gateway.complete()，见 app.llm_gateway。
    """
    warnings.warn("llm_complete 已废弃，请使用 gateway.complete()", DeprecationWarning, stacklevel=2)
    client = create_llm_client(api_key=api_key, base_url=base_url)
    response = await client.chat.completions.create(
        model=model or settings.MODEL_CONFIG__LLM__DEEPSEEK__DEFAULT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    return response.choices[0].message.content or ""
