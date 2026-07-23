"""语义缓存 — 命中缓存不重复调 LLM。"""

from __future__ import annotations

import hashlib
import time
from typing import Any


class SemanticCache:
    """语义缓存。

    基于文本精确匹配的缓存系统，相同查询命中不重复调用 LLM。
    后续可升级为向量语义匹配。
    """

    def __init__(self, ttl: int = 3600, max_size: int = 1000) -> None:
        """初始化语义缓存。

        Args:
            ttl: 缓存存活时间（秒），默认 1 小时。
            max_size: 最大缓存条目数。
        """
        self._ttl = ttl
        self._max_size = max_size
        self._cache: dict[str, dict[str, Any]] = {}

    def make_key(self, prompt: str, task_type: str = "") -> str:
        """生成缓存键。

        Args:
            prompt: 输入提示词。
            task_type: 任务类型。

        Returns:
            SHA-256 哈希后的缓存键。
        """
        raw = f"{task_type}::{prompt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        """获取缓存内容。

        Args:
            key: 缓存键。

        Returns:
            缓存的内容，不存在或已过期时返回 None。
        """
        entry = self._cache.get(key)
        if entry is None:
            return None

        # 检查是否过期
        if time.monotonic() - entry["time"] > self._ttl:
            del self._cache[key]
            return None

        return entry["content"]

    def set(self, key: str, content: str) -> None:
        """设置缓存。

        Args:
            key: 缓存键。
            content: 缓存内容。
        """
        # 如果缓存已满，删除最旧的条目
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["time"])
            del self._cache[oldest_key]

        self._cache[key] = {
            "content": content,
            "time": time.monotonic(),
        }

    def clear(self) -> None:
        """清除所有缓存。"""
        self._cache.clear()

    def invalidate(self, key: str) -> None:
        """使某缓存条目失效。

        Args:
            key: 缓存键。
        """
        self._cache.pop(key, None)

    @property
    def size(self) -> int:
        """当前缓存条目数。

        Returns:
            缓存条目数。
        """
        return len(self._cache)
