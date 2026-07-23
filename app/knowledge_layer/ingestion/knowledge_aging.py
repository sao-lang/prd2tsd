"""知识老化策略 — 90天降权 → 180天归档 → 365天软删除。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore

logger = get_logger("prd2tsd.knowledge.knowledge_aging")


class KnowledgeAgingPolicy:
    """知识老化策略执行器。"""

    def __init__(self, graph_store: Neo4jGraphStore | None = None) -> None:
        """初始化老化策略。

        Args:
            graph_store: Neo4j 图存储。为 None 时创建新实例。
        """
        self._graph_store = graph_store or Neo4jGraphStore()
        self._downgrade_days = kn_config.downgrade_days
        self._archive_days = kn_config.archive_days
        self._soft_delete_days = kn_config.soft_delete_days

    async def apply_aging(self, workspace_id: str = "") -> dict[str, int]:
        """执行知识老化策略。

        按时间逐级处理：降权 → 归档 → 软删除。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            {downgraded, archived, deleted} 统计。
        """
        stats: dict[str, int] = {"downgraded": 0, "archived": 0, "deleted": 0}
        now = datetime.now(UTC)

        downgrade_cutoff = now - timedelta(days=self._downgrade_days)
        archive_cutoff = now - timedelta(days=self._archive_days)
        delete_cutoff = now - timedelta(days=self._soft_delete_days)

        # 降权：90 天未更新
        stats["downgraded"] = await self._apply_downgrade(downgrade_cutoff, workspace_id)
        # 归档：180 天未更新
        stats["archived"] = await self._apply_archive(archive_cutoff, workspace_id)
        # 软删除：365 天未更新
        stats["deleted"] = await self._apply_soft_delete(delete_cutoff, workspace_id)

        logger.info(
            "知识老化完成: downgraded=%d, archived=%d, deleted=%d",
            stats["downgraded"],
            stats["archived"],
            stats["deleted"],
        )
        return stats

    async def _apply_downgrade(self, cutoff: datetime, workspace_id: str) -> int:
        """对截止时间前未更新的实体降权。

        Args:
            cutoff: 截止时间。
            workspace_id: 工作空间 ID。

        Returns:
            降权的实体数量。
        """
        cutoff_ts = int(cutoff.timestamp() * 1000)
        cypher = """
            MATCH (e:KGEntity)
            WHERE e.updated_at < $cutoff AND (e.status IS NULL OR e.status = 'active')
        """
        params: dict[str, Any] = {"cutoff": cutoff_ts}
        if workspace_id:
            cypher += " AND e.workspace_id = $workspace_id"
            params["workspace_id"] = workspace_id
        cypher += """
            SET e.status = 'downgraded',
                e.confidence = e.confidence * 0.5,
                e.downgraded_at = timestamp()
            RETURN count(e) AS cnt
        """
        records = await self._graph_store.run_cypher(cypher, params)
        return records[0]["cnt"] if records else 0

    async def _apply_archive(self, cutoff: datetime, workspace_id: str) -> int:
        """对截止时间前未更新的实体归档。

        Args:
            cutoff: 截止时间。
            workspace_id: 工作空间 ID。

        Returns:
            归档的实体数量。
        """
        cutoff_ts = int(cutoff.timestamp() * 1000)
        cypher = """
            MATCH (e:KGEntity)
            WHERE e.updated_at < $cutoff AND (e.status IS NULL OR e.status IN ['active', 'downgraded'])
        """
        params: dict[str, Any] = {"cutoff": cutoff_ts}
        if workspace_id:
            cypher += " AND e.workspace_id = $workspace_id"
            params["workspace_id"] = workspace_id
        cypher += """
            SET e.status = 'archived',
                e.archived_at = timestamp()
            RETURN count(e) AS cnt
        """
        records = await self._graph_store.run_cypher(cypher, params)
        return records[0]["cnt"] if records else 0

    async def _apply_soft_delete(self, cutoff: datetime, workspace_id: str) -> int:
        """对截止时间前未更新的实体软删除。

        Args:
            cutoff: 截止时间。
            workspace_id: 工作空间 ID。

        Returns:
            软删除的实体数量。
        """
        cutoff_ts = int(cutoff.timestamp() * 1000)
        cypher = """
            MATCH (e:KGEntity)
            WHERE e.updated_at < $cutoff AND (e.status IS NULL OR e.status <> 'deleted')
        """
        params: dict[str, Any] = {"cutoff": cutoff_ts}
        if workspace_id:
            cypher += " AND e.workspace_id = $workspace_id"
            params["workspace_id"] = workspace_id
        cypher += """
            SET e.status = 'deleted',
                e.deleted_at = timestamp()
            RETURN count(e) AS cnt
        """
        records = await self._graph_store.run_cypher(cypher, params)
        return records[0]["cnt"] if records else 0
