"""ragas 兼容 shim — 适配 langchain-community 拆分后的 vertexai 模块。

背景：`langchain-community>=0.4` 将 Google VertexAI 集成拆分到独立包，
而 `ragas 0.4.x` 仍在 `ragas/llms/base.py` 顶层导入
`langchain_community.chat_models.vertexai.ChatVertexAI`，导致
`import ragas` 时报 ModuleNotFoundError。

本模块在导入 ragas **之前**注册一个占位模块到
`sys.modules["langchain_community.chat_models.vertexai"]`，
仅满足 ragas 的导入与类型引用（`MULTIPLE_COMPLETION_SUPPORTED` 列表）。

> **注意**：项目不使用 Google VertexAI 模型；占位类不可实例化，
> 若误用会抛出 NotImplementedError。
"""

from __future__ import annotations

import sys
import types
from typing import Any


class _ChatVertexAIPlaceholder:
    """占位实现 — ragas 仅作类型引用，不参与实例化。

    Raises:
        NotImplementedError: 项目未启用 VertexAI 模型。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """占位构造 — 禁止实例化。

        Args:
            *args: 位置参数（未使用）。
            **kwargs: 关键字参数（未使用）。
        """
        raise NotImplementedError(
            "VertexAI 模型未启用，ChatVertexAI 仅为 ragas 兼容占位类，请勿实例化",
        )


def install_ragas_shims() -> None:
    """注册 langchain_community.chat_models.vertexai 兼容 shim。

    幂等：模块已注册或 langchain_community 不可用时直接返回。
    """
    if "langchain_community.chat_models.vertexai" in sys.modules:
        return
    try:
        import langchain_community.chat_models  # noqa: F401  # 确保父包已导入
    except ImportError:
        return
    module = types.ModuleType("langchain_community.chat_models.vertexai")
    module.ChatVertexAI = _ChatVertexAIPlaceholder
    sys.modules["langchain_community.chat_models.vertexai"] = module
