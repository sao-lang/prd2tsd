"""连接器抽象基类与健康状态模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.connections")


@dataclass
class ConnHealth:
    """连接健康状态。"""

    name: str
    connected: bool
    enabled: bool
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseConnector:
    """连接器抽象基类。"""

    def __init__(self, name: str, enabled: bool = False) -> None:
        """初始化连接器。

        Args:
            name: 连接器名称。
            enabled: 是否启用（已连接）。
        """
        self.name = name
        self.enabled = enabled
        self._connected = False

    async def connect(self) -> bool:
        """建立连接。子类必须实现。

        Returns:
            是否连接成功。
        """
        raise NotImplementedError

    async def disconnect(self) -> None:
        """断开连接。子类必须实现。"""
        raise NotImplementedError

    def is_connected(self) -> bool:
        """检查连接状态。

        Returns:
            是否已连接。
        """
        return self._connected

    async def health(self) -> ConnHealth:
        """返回健康状态。子类应覆盖以实现具体检测。

        Returns:
            连接健康状态。
        """
        return ConnHealth(
            name=self.name,
            connected=self._connected,
            enabled=self.enabled,
        )
