"""工具执行上下文 — 每个工具执行时注入。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """工具执行上下文 — 每个工具执行时注入。

    提供工具执行所需的所有依赖：
    - state: 当前 Agent State 的快照
    - llm: LLM 调用能力（工具也可调 LLM）
    - services: 其他外部服务
    """

    task_id: str = ""
    workspace_id: str = ""
    user_id: str = ""
    trace_id: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    llm: Any = None
    db: Any = None
    services: dict[str, Any] = field(default_factory=dict)
