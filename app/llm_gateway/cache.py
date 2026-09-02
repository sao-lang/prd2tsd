"""多级 LLM 语义缓存：本地精确命中 + PostgreSQL 持久化语义匹配。"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.models.block_e import SemanticCacheEntry

logger = get_logger("prd2tsd.semantic_cache")

type EmbeddingLoader = Callable[[str], Awaitable[tuple[list[float], str]]]


@dataclass
class CacheCandidate:
    """语义缓存候选。"""

    prompt_hash: str
    response: str
    embedding: list[float]


class SemanticCacheStore(Protocol):
    """持久化语义缓存接口。"""

    async def candidates(
        self,
        workspace_id: str,
        task_type: str,
        model: str,
        embedding_model: str,
        guardrail_version: str,
        limit: int,
    ) -> list[CacheCandidate]: ...

    async def upsert(
        self,
        *,
        workspace_id: str,
        task_type: str,
        model: str,
        prompt_hash: str,
        response: str,
        embedding: list[float],
        embedding_model: str,
        guardrail_version: str,
        expires_at: datetime,
    ) -> None: ...


class PostgresSemanticCacheStore:
    """SQLAlchemy 语义缓存存储。"""

    @staticmethod
    def _session() -> Any:
        return connection_manager.get("postgres").get_session()

    async def candidates(
        self,
        workspace_id: str,
        task_type: str,
        model: str,
        embedding_model: str,
        guardrail_version: str,
        limit: int,
    ) -> list[CacheCandidate]:
        async with self._session() as session:
            rows = (
                await session.scalars(
                    select(SemanticCacheEntry)
                    .where(
                        SemanticCacheEntry.workspace_id == workspace_id,
                        SemanticCacheEntry.task_type == task_type,
                        SemanticCacheEntry.model == model,
                        SemanticCacheEntry.embedding_model == embedding_model,
                        SemanticCacheEntry.guardrail_version == guardrail_version,
                        SemanticCacheEntry.expires_at > datetime.now(UTC),
                    )
                    .order_by(SemanticCacheEntry.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return [
                CacheCandidate(
                    prompt_hash=row.prompt_hash,
                    response=row.response,
                    embedding=[float(value) for value in row.embedding],
                )
                for row in rows
            ]

    async def upsert(
        self,
        *,
        workspace_id: str,
        task_type: str,
        model: str,
        prompt_hash: str,
        response: str,
        embedding: list[float],
        embedding_model: str,
        guardrail_version: str,
        expires_at: datetime,
    ) -> None:
        async with self._session() as session:
            row = await session.scalar(
                select(SemanticCacheEntry).where(
                    SemanticCacheEntry.workspace_id == workspace_id,
                    SemanticCacheEntry.task_type == task_type,
                    SemanticCacheEntry.model == model,
                    SemanticCacheEntry.prompt_hash == prompt_hash,
                    SemanticCacheEntry.embedding_model == embedding_model,
                    SemanticCacheEntry.guardrail_version == guardrail_version,
                )
            )
            if row is None:
                row = SemanticCacheEntry(
                    workspace_id=workspace_id,
                    task_type=task_type,
                    model=model,
                    prompt_hash=prompt_hash,
                    response=response,
                    embedding=embedding,
                    embedding_model=embedding_model,
                    guardrail_version=guardrail_version,
                    expires_at=expires_at,
                )
                session.add(row)
            else:
                row.response = response
                row.embedding = embedding
                row.expires_at = expires_at
            await session.commit()


class MemorySemanticCacheStore:
    """仅供单元测试使用的语义缓存存储。"""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def candidates(
        self,
        workspace_id: str,
        task_type: str,
        model: str,
        embedding_model: str,
        guardrail_version: str,
        limit: int,
    ) -> list[CacheCandidate]:
        now = datetime.now(UTC)
        matched = [
            entry
            for entry in reversed(self.entries)
            if entry["workspace_id"] == workspace_id
            and entry["task_type"] == task_type
            and entry["model"] == model
            and entry["embedding_model"] == embedding_model
            and entry["guardrail_version"] == guardrail_version
            and entry["expires_at"] > now
        ]
        return [
            CacheCandidate(entry["prompt_hash"], entry["response"], entry["embedding"]) for entry in matched[:limit]
        ]

    async def upsert(self, **entry: Any) -> None:
        self.entries = [
            current
            for current in self.entries
            if not all(
                current.get(key) == entry.get(key)
                for key in (
                    "workspace_id",
                    "task_type",
                    "model",
                    "prompt_hash",
                    "embedding_model",
                    "guardrail_version",
                )
            )
        ]
        self.entries.append(dict(entry))


class SemanticCache:
    """在严格租户/任务/模型边界内执行精确和余弦语义匹配。"""

    def __init__(
        self,
        ttl: int | None = None,
        max_size: int = 1000,
        similarity_threshold: float | None = None,
        store: SemanticCacheStore | None = None,
        enabled: bool | None = None,
    ) -> None:
        """初始化多级缓存。"""
        self._ttl = ttl if ttl is not None else settings.SEMANTIC_CACHE_TTL_SECONDS
        self._max_size = max_size
        self._threshold = (
            similarity_threshold if similarity_threshold is not None else settings.SEMANTIC_CACHE_SIMILARITY_THRESHOLD
        )
        self._enabled = settings.SEMANTIC_CACHE_ENABLED if enabled is None else enabled
        self._store = store or PostgresSemanticCacheStore()
        self._cache: dict[str, dict[str, Any]] = {}
        self._pending_embeddings: dict[str, tuple[list[float], str]] = {}

    def make_key(
        self,
        prompt: str,
        task_type: str = "",
        workspace_id: str = "",
        model: str = "",
    ) -> str:
        """生成包含租户、任务、模型及护栏版本的精确缓存键。"""
        raw = f"{workspace_id}::{task_type}::{model}::{settings.SEMANTIC_CACHE_GUARDRAIL_VERSION}::{prompt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        """读取进程内一级精确缓存。"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry["time"] > self._ttl:
            del self._cache[key]
            return None
        return str(entry["content"])

    def set(self, key: str, content: str) -> None:
        """写入进程内一级精确缓存。"""
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda cache_key: self._cache[cache_key]["time"])
            del self._cache[oldest_key]
        self._cache[key] = {"content": content, "time": time.monotonic()}

    async def lookup(
        self,
        *,
        prompt: str,
        task_type: str,
        workspace_id: str,
        model: str,
        embedding_loader: EmbeddingLoader,
    ) -> str | None:
        """先精确命中，再对持久化候选执行余弦语义匹配。"""
        key = self.make_key(prompt, task_type, workspace_id, model)
        exact = self.get(key)
        # 无租户边界时仅允许精确命中，禁止相似问题在匿名调用之间复用。
        if exact is not None or not self._enabled or not workspace_id:
            return exact

        try:
            embedding, embedding_model = await embedding_loader(prompt)
        except Exception as exc:  # 第三方/本地向量模型是缓存边界，失败必须降级而非中断主调用。
            logger.warning("语义缓存向量生成失败，降级为精确缓存: %s", exc)
            return None
        if not embedding:
            return None
        self._pending_embeddings[key] = (embedding, embedding_model)
        if len(self._pending_embeddings) > self._max_size:
            self._pending_embeddings.pop(next(iter(self._pending_embeddings)))
        try:
            candidates = await self._store.candidates(
                workspace_id,
                task_type,
                model,
                embedding_model,
                settings.SEMANTIC_CACHE_GUARDRAIL_VERSION,
                settings.SEMANTIC_CACHE_MAX_CANDIDATES,
            )
        except (KeyError, RuntimeError, OSError, SQLAlchemyError) as exc:
            logger.warning("语义缓存存储不可用，降级为精确缓存: %s", exc)
            return None

        best: CacheCandidate | None = None
        best_score = -1.0
        for candidate in candidates:
            score = self._cosine_similarity(embedding, candidate.embedding)
            if score > best_score:
                best, best_score = candidate, score
        if best is not None and best_score >= self._threshold:
            self._pending_embeddings.pop(key, None)
            self.set(key, best.response)
            return best.response
        return None

    async def store(
        self,
        *,
        prompt: str,
        response: str,
        task_type: str,
        workspace_id: str,
        model: str,
        embedding_loader: EmbeddingLoader,
    ) -> None:
        """写入精确缓存及持久化语义条目。"""
        key = self.make_key(prompt, task_type, workspace_id, model)
        self.set(key, response)
        if not self._enabled or not workspace_id:
            return
        pending = self._pending_embeddings.pop(key, None)
        try:
            embedding, embedding_model = pending or await embedding_loader(prompt)
        except Exception as exc:  # 缓存写入不得影响已成功的模型响应。
            logger.warning("语义缓存向量生成失败，已保留精确缓存: %s", exc)
            return
        if not embedding:
            return
        try:
            await self._store.upsert(
                workspace_id=workspace_id,
                task_type=task_type,
                model=model,
                prompt_hash=key,
                response=response,
                embedding=embedding,
                embedding_model=embedding_model,
                guardrail_version=settings.SEMANTIC_CACHE_GUARDRAIL_VERSION,
                expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl),
            )
        except (KeyError, RuntimeError, OSError, SQLAlchemyError) as exc:
            logger.warning("语义缓存持久化失败，已保留精确缓存: %s", exc)

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        """计算等维向量余弦相似度。"""
        if not left or len(left) != len(right):
            return -1.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return -1.0
        return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)

    def clear(self) -> None:
        """清除进程内一级缓存。"""
        self._cache.clear()
        self._pending_embeddings.clear()

    def invalidate(self, key: str) -> None:
        """使进程内精确缓存条目失效。"""
        self._cache.pop(key, None)

    @property
    def size(self) -> int:
        """返回进程内缓存条目数。"""
        return len(self._cache)
