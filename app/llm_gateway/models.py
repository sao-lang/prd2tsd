"""LLM Gateway 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """聊天消息。"""

    role: str  # system / user / assistant
    content: str


@dataclass
class CompletionUsage:
    """Token 使用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """LLM 生成响应。"""

    content: str
    model: str = ""
    cached: bool = False
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingResponse:
    """Embedding 响应。"""

    embeddings: list[list[float]]
    model: str = ""
    input_tokens: int = 0
    cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RerankResponse:
    """Rerank 响应。"""

    scores: list[float]
    indices: list[int]
    model: str = ""
    input_tokens: int = 0
    cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
