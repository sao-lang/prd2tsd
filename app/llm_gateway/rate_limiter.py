"""速率限制器 — 基于 Token 桶的流控。"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("prd2tsd.ratelimit")


class RateLimiter:
    """速率限制器。

    支持两种限制维度：
    - RPM（Requests Per Minute）：每分钟最大请求数
    - TPM（Tokens Per Minute）：每分钟最大 Token 数

    基于滑动窗口算法实现。
    """

    def __init__(
        self,
        default_rpm: int = 0,
        default_tpm: int = 0,
    ) -> None:
        """初始化速率限制器。

        Args:
            default_rpm: 默认每分钟最大请求数，0 表示不限制。
            default_tpm: 默认每分钟最大 Token 数，0 表示不限制。
        """
        self._default_rpm = default_rpm or int(settings.RATE_LIMIT_DEFAULT_RPM)
        self._default_tpm = default_tpm or int(settings.RATE_LIMIT_DEFAULT_TPM)

        # 滑动窗口记录: {workspace_id: [(timestamp, tokens), ...]}
        self._request_log: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._window_seconds = 60

        # 自定义限制: {workspace_id: {"rpm": int, "tpm": int}}
        self._custom_limits: dict[str, dict[str, int]] = {}
        self._lock = Lock()

    def set_limit(
        self,
        workspace_id: str,
        rpm: int | None = None,
        tpm: int | None = None,
    ) -> None:
        """设置工作空间的自定义限制。

        Args:
            workspace_id: 工作空间 ID。
            rpm: 每分钟最大请求数。
            tpm: 每分钟最大 Token 数。
        """
        limit = self._custom_limits.get(workspace_id, {})
        if rpm is not None:
            limit["rpm"] = rpm
        if tpm is not None:
            limit["tpm"] = tpm
        self._custom_limits[workspace_id] = limit
        logger.info(
            "工作空间 %s 速率限制已设置: rpm=%s, tpm=%s",
            workspace_id, rpm, tpm,
        )

    async def check(
        self,
        workspace_id: str,
        tokens: int = 0,
    ) -> dict[str, Any]:
        """检查是否允许本次请求。

        清理过期记录后判断 RPM 和 TPM 是否超限。

        Args:
            workspace_id: 工作空间 ID。
            tokens: 本次请求预计消耗的 Token 数。

        Returns:
            检查结果：{
                "allowed": bool,
                "retry_after": float,   # 需要等待的秒数（超限时）
                "remaining_rpm": int,
                "remaining_tpm": int,
            }
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds
        limits = self._custom_limits.get(workspace_id, {})
        max_rpm = limits.get("rpm", self._default_rpm)
        max_tpm = limits.get("tpm", self._default_tpm)

        with self._lock:
            # 清理过期记录
            log = self._request_log[workspace_id]
            self._request_log[workspace_id] = [
                (ts, tk) for ts, tk in log if ts > cutoff
            ]
            log = self._request_log[workspace_id]

            # 计算当前窗口使用量
            current_rpm = len(log)
            current_tpm = sum(tk for _, tk in log)

        result: dict[str, Any] = {
            "allowed": True,
            "retry_after": 0.0,
            "remaining_rpm": max(0, max_rpm - current_rpm) if max_rpm > 0 else -1,
            "remaining_tpm": max(0, max_tpm - current_tpm) if max_tpm > 0 else -1,
        }

        # 检查 RPM 限制
        if max_rpm > 0 and current_rpm >= max_rpm:
            oldest = log[0][0] if log else now
            result["allowed"] = False
            result["retry_after"] = max(result["retry_after"], cutoff + self._window_seconds - oldest)
            result["remaining_rpm"] = 0

        # 检查 TPM 限制
        if max_tpm > 0 and current_tpm + tokens > max_tpm:
            result["allowed"] = False
            if result["retry_after"] == 0.0 and log:
                oldest = log[0][0]
                result["retry_after"] = max(result["retry_after"], cutoff + self._window_seconds - oldest)

        return result

    async def record(self, workspace_id: str, tokens: int = 0) -> None:
        """记录一次请求。

        Args:
            workspace_id: 工作空间 ID。
            tokens: 消耗的 Token 数。
        """
        with self._lock:
            self._request_log[workspace_id].append((time.monotonic(), tokens))

    def reset(self, workspace_id: str | None = None) -> None:
        """重置限制记录。

        Args:
            workspace_id: 指定工作空间。为 None 时重置所有记录。
        """
        with self._lock:
            if workspace_id:
                self._request_log.pop(workspace_id, None)
            else:
                self._request_log.clear()


# 全局单例
rate_limiter = RateLimiter()
