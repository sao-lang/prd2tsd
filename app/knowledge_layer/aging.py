"""知识图谱实体与关系的生命周期老化策略。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.knowledge_layer.config import KnowledgeLayerConfig, kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KnowledgeAgingStats


class KnowledgeAgingPolicy:
    """按最后更新时间执行降级、归档和软删除。"""

    def __init__(
        self,
        graph_store: Neo4jGraphStore | None = None,
        config: KnowledgeLayerConfig | None = None,
    ) -> None:
        self._graph_store = graph_store or Neo4jGraphStore()
        self._config = config or kn_config

    async def run(
        self,
        workspace_id: str = "",
        now: datetime | None = None,
    ) -> KnowledgeAgingStats:
        """执行一次知识老化。

        Args:
            workspace_id: 可选工作空间；为空时处理全部工作空间。
            now: 测试或补偿任务使用的基准时间，默认当前 UTC 时间。

        Returns:
            实体和关系在各阶段的变更数量。
        """
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        return await self._graph_store.apply_aging(
            downgrade_before_ms=self._to_epoch_ms(reference - timedelta(days=self._config.downgrade_days)),
            archive_before_ms=self._to_epoch_ms(reference - timedelta(days=self._config.archive_days)),
            soft_delete_before_ms=self._to_epoch_ms(reference - timedelta(days=self._config.soft_delete_days)),
            workspace_id=workspace_id,
        )

    @staticmethod
    def _to_epoch_ms(value: datetime) -> int:
        """把带时区时间转换为 Neo4j ``timestamp()`` 使用的毫秒值。"""
        return int(value.timestamp() * 1000)
