"""知识图谱版本控制 — 快照创建 → 回滚 → 差异查看。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.graph_store import Neo4jGraphStore

logger = get_logger("prd2tsd.knowledge.kg_versioning")


class KnowledgeGraphVersioning:
    """知识图谱版本控制器。

    通过导出/导入 Neo4j 子图实现快照和回滚。
    版本元数据存储在 Neo4j 的 VersionSnapshot 节点中。
    """

    def __init__(self, graph_store: Neo4jGraphStore | None = None) -> None:
        """初始化版本控制器。

        Args:
            graph_store: Neo4j 图存储。为 None 时创建新实例。
        """
        self._graph_store = graph_store or Neo4jGraphStore()

    async def create_snapshot(
        self,
        name: str,
        workspace_id: str = "",
    ) -> str:
        """创建知识图谱快照。

        Args:
            name: 快照名称。
            workspace_id: 工作空间 ID。

        Returns:
            快照 ID。
        """
        snapshot_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        # 导出当前图谱
        entities, relations = await self._export_graph(workspace_id)

        # 存储快照元数据到 Neo4j
        await self._graph_store.run_cypher(
            """
            CREATE (v:VersionSnapshot {
                id: $id,
                name: $name,
                created_at: $created_at,
                entity_count: $entity_count,
                relation_count: $relation_count,
                workspace_id: $workspace_id
            })
            """,
            {
                "id": snapshot_id,
                "name": name,
                "created_at": now,
                "entity_count": len(entities),
                "relation_count": len(relations),
                "workspace_id": workspace_id,
            },
        )

        # 将快照数据存为节点属性（也可存到外部存储，简化版存节点）
        await self._graph_store.run_cypher(
            """
            MATCH (v:VersionSnapshot {id: $id})
            SET v.snapshot_data = $data
            """,
            {
                "id": snapshot_id,
                "data": json.dumps({"entities": entities, "relations": relations}, ensure_ascii=False),
            },
        )

        logger.info(
            "版本快照已创建: %s (entities=%d, relations=%d)",
            name,
            len(entities),
            len(relations),
        )
        return snapshot_id

    async def rollback(self, snapshot_id: str) -> bool:
        """回滚到指定版本快照。

        Args:
            snapshot_id: 快照 ID。

        Returns:
            是否成功回滚。
        """
        # 获取快照数据
        records = await self._graph_store.run_cypher(
            "MATCH (v:VersionSnapshot {id: $id}) RETURN v.snapshot_data AS data, v.workspace_id AS workspace_id",
            {"id": snapshot_id},
        )
        if not records:
            logger.warning("快照不存在: %s", snapshot_id)
            return False

        record = records[0]
        workspace_id = record.get("workspace_id", "")
        snapshot_data = json.loads(record["data"])

        # 清空当前工作空间的数据
        await self._clear_workspace(workspace_id)

        # 恢复实体
        entities = snapshot_data.get("entities", [])
        for entity in entities:
            await self._graph_store.run_cypher(
                """
                CREATE (e:KGEntity {
                    id: $id, name: $name, type: $type,
                    category: $category, description: $description,
                    confidence: $confidence, workspace_id: $workspace_id,
                    created_at: timestamp(), updated_at: timestamp()
                })
                """,
                entity,
            )

        # 恢复关系
        relations = snapshot_data.get("relations", [])
        for relation in relations:
            await self._graph_store.run_cypher(
                """
                MATCH (source:KGEntity {id: $source_id})
                MATCH (target:KGEntity {id: $target_id})
                MERGE (source)-[r:KGRelation {
                    id: $id, type: $type, reason: $reason,
                    confidence: $confidence, workspace_id: $workspace_id
                }]->(target)
                """,
                relation,
            )

        logger.info(
            "已回滚到快照 %s: %d entities, %d relations",
            snapshot_id,
            len(entities),
            len(relations),
        )
        return True

    async def list_snapshots(self, workspace_id: str = "") -> list[dict[str, Any]]:
        """列出所有版本快照。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            快照元数据列表。
        """
        cypher = "MATCH (v:VersionSnapshot) RETURN v ORDER BY v.created_at DESC"
        params: dict[str, Any] = {}
        if workspace_id:
            cypher = "MATCH (v:VersionSnapshot {workspace_id: $workspace_id}) RETURN v ORDER BY v.created_at DESC"
            params["workspace_id"] = workspace_id

        records = await self._graph_store.run_cypher(cypher, params)
        snapshots: list[dict[str, Any]] = []
        for record in records:
            v = dict(record["v"])
            v.pop("snapshot_data", None)
            snapshots.append(v)
        return snapshots

    async def _export_graph(
        self,
        workspace_id: str = "",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """导出当前图谱数据。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            (实体数据列表, 关系数据列表)。
        """
        entities_query = "MATCH (e:KGEntity) RETURN e"
        relations_query = """
            MATCH (source:KGEntity)-[r:KGRelation]->(target:KGEntity)
            RETURN r, source.id AS source_id, target.id AS target_id
        """
        params: dict[str, Any] = {}
        if workspace_id:
            entities_query = "MATCH (e:KGEntity {workspace_id: $workspace_id}) RETURN e"
            relations_query = """
                MATCH (source:KGEntity {workspace_id: $workspace_id})
                -[r:KGRelation]->(target:KGEntity {workspace_id: $workspace_id})
                RETURN r, source.id AS source_id, target.id AS target_id
            """
            params["workspace_id"] = workspace_id

        entity_records = await self._graph_store.run_cypher(entities_query, params)
        relation_records = await self._graph_store.run_cypher(relations_query, params)

        entities: list[dict[str, Any]] = []
        for record in entity_records:
            node = dict(record["e"])
            entities.append(node)

        relations: list[dict[str, Any]] = []
        for record in relation_records:
            rel = dict(record["r"])
            rel["source_id"] = record.get("source_id", "")
            rel["target_id"] = record.get("target_id", "")
            relations.append(rel)

        return entities, relations

    async def _clear_workspace(self, workspace_id: str) -> None:
        """清空工作空间的数据。

        Args:
            workspace_id: 工作空间 ID。
        """
        if workspace_id:
            await self._graph_store.run_cypher(
                "MATCH (e:KGEntity {workspace_id: $workspace_id}) DETACH DELETE e",
                {"workspace_id": workspace_id},
            )
            await self._graph_store.run_cypher(
                "MATCH (e:TextUnit {workspace_id: $workspace_id}) DETACH DELETE e",
                {"workspace_id": workspace_id},
            )
        else:
            await self._graph_store.run_cypher("MATCH (e:KGEntity) DETACH DELETE e")
            await self._graph_store.run_cypher("MATCH (e:TextUnit) DETACH DELETE e")
