"""Neo4j 图存储封装 — 实体的 CRUD 操作。"""

from __future__ import annotations

import uuid
from typing import Any, cast

from neo4j import AsyncDriver

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import BuildStats, KGEntity, KGRelation, KnowledgeAgingStats

logger = get_logger("prd2tsd.knowledge.graph_store")


class Neo4jGraphStore:
    """Neo4j 图存储封装。"""

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        """初始化 Neo4j 存储。

        Args:
            driver: Neo4j 异步驱动。为 None 时从 ConnectionManager 获取。
        """
        self._driver = driver
        self._database = kn_config.neo4j_database

    async def _get_driver(self) -> AsyncDriver:
        """获取 Neo4j 驱动。

        Returns:
            AsyncDriver 实例。
        """
        if self._driver is not None:
            return self._driver
        connector = connection_manager.get("neo4j")
        return cast(AsyncDriver, connector.get_driver())

    async def upsert_entity(self, entity: KGEntity) -> str:
        """创建或更新实体节点。

        Args:
            entity: 实体对象。

        Returns:
            实体 ID。
        """
        entity_id = entity.id or str(uuid.uuid4())
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            await session.run(
                """
                MERGE (e:KGEntity {id: $id})
                ON CREATE SET e.created_at = timestamp()
                SET e.name = $name,
                    e.type = $type,
                    e.category = $category,
                    e.description = $description,
                    e.properties = $properties,
                    e.confidence = $confidence,
                    e.workspace_id = $workspace_id,
                    e.source_text_unit_id = $source_text_unit_id,
                    e.status = 'active',
                    e.updated_at = timestamp()
                REMOVE e.archived_at, e.deleted_at
                """,
                id=entity_id,
                name=entity.name,
                type=entity.type,
                category=entity.category,
                description=entity.description,
                properties=str(entity.properties),
                confidence=entity.confidence,
                workspace_id=entity.workspace_id,
                source_text_unit_id=entity.source_text_unit_id,
            )
        logger.debug("实体已保存: %s (%s)", entity.name, entity_id)
        return entity_id

    async def get_stats(self) -> BuildStats:
        """统计当前图谱中的实体与关系数量。

        Returns:
            BuildStats（entities/relations 为全库计数，chunks/claims 为 0）。
        """
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            entity_result = await session.run("MATCH (e:KGEntity) RETURN count(e) AS c")
            entity_row = await entity_result.single()
            entity_count = int(entity_row["c"]) if entity_row else 0

            relation_result = await session.run("MATCH ()-[r]->() RETURN count(r) AS c")
            relation_row = await relation_result.single()
            relation_count = int(relation_row["c"]) if relation_row else 0
        return BuildStats(entities=entity_count, relations=relation_count)

    async def upsert_entities(self, entities: list[KGEntity]) -> list[str]:
        """批量创建或更新实体。

        Args:
            entities: 实体列表。

        Returns:
            实体 ID 列表。
        """
        return [await self.upsert_entity(e) for e in entities]

    async def upsert_relation(self, relation: KGRelation) -> str:
        """幂等创建或更新实体关系。

        固定使用 ``RELATED`` 关系类型，模型输出仅作为属性写入，禁止动态拼接 Cypher。
        """
        relation_id = relation.id or str(uuid.uuid4())
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            result = await session.run(
                """
                MATCH (source:KGEntity {id: $source_id, workspace_id: $workspace_id})
                MATCH (target:KGEntity {id: $target_id, workspace_id: $workspace_id})
                MERGE (source)-[r:RELATED {id: $id}]->(target)
                ON CREATE SET r.created_at = timestamp()
                SET r.relation_type = $relation_type,
                    r.description = $description,
                    r.confidence = $confidence,
                    r.source_text_unit_id = $source_text_unit_id,
                    r.workspace_id = $workspace_id,
                    r.status = 'active',
                    r.updated_at = timestamp()
                REMOVE r.archived_at, r.deleted_at
                RETURN r.id AS id
                """,
                id=relation_id,
                source_id=relation.source_entity_id,
                target_id=relation.target_entity_id,
                relation_type=relation.relation_type,
                description=relation.description,
                confidence=relation.confidence,
                source_text_unit_id=relation.source_text_unit_id,
                workspace_id=relation.workspace_id,
            )
            record = await result.single()
        if record is None:
            raise ValueError(
                f"关系端点不存在或不属于同一工作空间: {relation.source_entity_id} -> {relation.target_entity_id}"
            )
        return str(record["id"])

    async def upsert_relations(self, relations: list[KGRelation]) -> list[str]:
        """批量幂等写入实体关系。"""
        return [await self.upsert_relation(relation) for relation in relations]

    async def get_entity(self, entity_id: str) -> KGEntity | None:
        """根据 ID 获取实体。

        Args:
            entity_id: 实体 ID。

        Returns:
            实体对象，不存在时返回 None。
        """
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            result = await session.run(
                "MATCH (e:KGEntity {id: $id}) RETURN e",
                id=entity_id,
            )
            record = await result.single()
        if record is None:
            return None
        return self._record_to_entity(record["e"])

    async def get_entity_by_name(self, name: str, workspace_id: str = "") -> KGEntity | None:
        """根据名称获取实体。

        Args:
            name: 实体名称。
            workspace_id: 工作空间 ID。

        Returns:
            实体对象，不存在时返回 None。
        """
        driver = await self._get_driver()
        query = "MATCH (e:KGEntity {name: $name})"
        params: dict[str, Any] = {"name": name}
        if workspace_id:
            query += " WHERE e.workspace_id = $workspace_id"
            params["workspace_id"] = workspace_id
        query += " RETURN e LIMIT 1"
        async with driver.session(database=self._database) as session:
            # 参数以 dict 形式作为 parameters 传入，避免 params 含 query 键与位置参数冲突
            result = await session.run(query, params)
            record = await result.single()
        if record is None:
            return None
        return self._record_to_entity(record["e"])

    async def search_entities(
        self,
        query: str,
        workspace_id: str = "",
        limit: int = 10,
    ) -> list[KGEntity]:
        """按名称模糊搜索实体。

        Args:
            query: 搜索关键词。
            workspace_id: 工作空间 ID。
            limit: 返回数量限制。

        Returns:
            匹配的实体列表。
        """
        driver = await self._get_driver()
        cypher = """
            MATCH (e:KGEntity)
            WHERE e.name CONTAINS $query
              AND coalesce(e.status, 'active') IN ['active', 'downgraded']
        """
        params: dict[str, Any] = {"query": query, "limit": limit}
        if workspace_id:
            cypher += " AND e.workspace_id = $workspace_id"
        cypher += " RETURN e LIMIT $limit"
        async with driver.session(database=self._database) as session:
            # 参数以 dict 形式传入，避免 params 中的 query 键与位置参数冲突
            result = await session.run(cypher, params)
            records = await result.fetch(limit)
        return [self._record_to_entity(r["e"]) for r in records]

    async def get_neighbors(
        self,
        entity_id: str,
        max_depth: int = 2,
        workspace_id: str = "",
    ) -> list[KGEntity]:
        """获取实体的邻接实体。

        Args:
            entity_id: 中心实体 ID。
            max_depth: 最大遍历深度。
            workspace_id: 工作空间 ID。

        Returns:
            邻接实体列表。
        """
        driver = await self._get_driver()
        cypher = """
            MATCH path = (e:KGEntity {id: $entity_id})-[*1..$max_depth]-(neighbor)
            WHERE coalesce(e.status, 'active') IN ['active', 'downgraded']
              AND coalesce(neighbor.status, 'active') IN ['active', 'downgraded']
              AND all(rel IN relationships(path)
                      WHERE coalesce(rel.status, 'active') IN ['active', 'downgraded'])
            UNWIND nodes(path) AS n
            RETURN COLLECT(DISTINCT n) AS entities
        """
        params: dict[str, Any] = {"entity_id": entity_id, "max_depth": max_depth}
        if workspace_id:
            cypher = cypher.replace(
                "MATCH path = (e:KGEntity {id: $entity_id})",
                "MATCH path = (e:KGEntity {id: $entity_id, workspace_id: $workspace_id})",
            )
            params["workspace_id"] = workspace_id
        async with driver.session(database=self._database) as session:
            result = await session.run(cypher, params)
            record = await result.single()
        if record is None:
            return []
        return [self._record_to_entity(n) for n in record["entities"]]

    async def get_all_entities(self, workspace_id: str = "") -> list[KGEntity]:
        """获取所有实体（用于老化/备份等）。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            实体列表。
        """
        driver = await self._get_driver()
        cypher = "MATCH (e:KGEntity)"
        params: dict[str, Any] = {}
        if workspace_id:
            cypher += (
                " WHERE e.workspace_id = $workspace_id"
                " AND coalesce(e.status, 'active') IN ['active', 'downgraded']"
            )
            params["workspace_id"] = workspace_id
        else:
            cypher += " WHERE coalesce(e.status, 'active') IN ['active', 'downgraded']"
        cypher += " RETURN e"
        async with driver.session(database=self._database) as session:
            result = await session.run(cypher, params)
            records = await result.fetch(10000)
        return [self._record_to_entity(r["e"]) for r in records]

    async def apply_aging(
        self,
        downgrade_before_ms: int,
        archive_before_ms: int,
        soft_delete_before_ms: int,
        workspace_id: str = "",
    ) -> KnowledgeAgingStats:
        """按更新时间对实体及关系执行降级、归档和软删除。

        最老数据先软删除，其次归档，最后降级，确保一次任务中状态不会被较轻阶段覆盖。
        """
        driver = await self._get_driver()
        params: dict[str, Any] = {
            "downgrade_before": downgrade_before_ms,
            "archive_before": archive_before_ms,
            "soft_delete_before": soft_delete_before_ms,
            "workspace_id": workspace_id,
        }
        workspace_filter_entity = "AND ($workspace_id = '' OR e.workspace_id = $workspace_id)"
        workspace_filter_relation = "AND ($workspace_id = '' OR r.workspace_id = $workspace_id)"

        async with driver.session(database=self._database) as session:
            await session.run(
                """
                MATCH (e:KGEntity)
                WHERE e.updated_at IS NULL
                  AND ($workspace_id = '' OR e.workspace_id = $workspace_id)
                SET e.updated_at = coalesce(e.created_at, timestamp())
                """,
                params,
            )
            await session.run(
                """
                MATCH ()-[r:RELATED]->()
                WHERE r.updated_at IS NULL
                  AND ($workspace_id = '' OR r.workspace_id = $workspace_id)
                SET r.updated_at = coalesce(r.created_at, timestamp())
                """,
                params,
            )
            deleted_entities = await self._aging_count(
                session,
                f"""
                MATCH (e:KGEntity)
                WHERE coalesce(e.status, 'active') <> 'deleted'
                  AND coalesce(e.updated_at, 0) < $soft_delete_before
                  {workspace_filter_entity}
                SET e.status = 'deleted', e.deleted_at = timestamp()
                RETURN count(e) AS changed
                """,
                params,
            )
            archived_entities = await self._aging_count(
                session,
                f"""
                MATCH (e:KGEntity)
                WHERE coalesce(e.status, 'active') IN ['active', 'downgraded']
                  AND coalesce(e.updated_at, 0) < $archive_before
                  {workspace_filter_entity}
                SET e.status = 'archived', e.archived_at = timestamp()
                RETURN count(e) AS changed
                """,
                params,
            )
            downgraded_entities = await self._aging_count(
                session,
                f"""
                MATCH (e:KGEntity)
                WHERE coalesce(e.status, 'active') = 'active'
                  AND coalesce(e.updated_at, 0) < $downgrade_before
                  {workspace_filter_entity}
                SET e.status = 'downgraded'
                RETURN count(e) AS changed
                """,
                params,
            )
            deleted_relations = await self._aging_count(
                session,
                f"""
                MATCH ()-[r:RELATED]->()
                WHERE coalesce(r.status, 'active') <> 'deleted'
                  AND coalesce(r.updated_at, 0) < $soft_delete_before
                  {workspace_filter_relation}
                SET r.status = 'deleted', r.deleted_at = timestamp()
                RETURN count(r) AS changed
                """,
                params,
            )
            archived_relations = await self._aging_count(
                session,
                f"""
                MATCH ()-[r:RELATED]->()
                WHERE coalesce(r.status, 'active') IN ['active', 'downgraded']
                  AND coalesce(r.updated_at, 0) < $archive_before
                  {workspace_filter_relation}
                SET r.status = 'archived', r.archived_at = timestamp()
                RETURN count(r) AS changed
                """,
                params,
            )
            downgraded_relations = await self._aging_count(
                session,
                f"""
                MATCH ()-[r:RELATED]->()
                WHERE coalesce(r.status, 'active') = 'active'
                  AND coalesce(r.updated_at, 0) < $downgrade_before
                  {workspace_filter_relation}
                SET r.status = 'downgraded'
                RETURN count(r) AS changed
                """,
                params,
            )

        return KnowledgeAgingStats(
            downgraded_entities=downgraded_entities,
            archived_entities=archived_entities,
            deleted_entities=deleted_entities,
            downgraded_relations=downgraded_relations,
            archived_relations=archived_relations,
            deleted_relations=deleted_relations,
        )

    @staticmethod
    async def _aging_count(session: Any, query: str, params: dict[str, Any]) -> int:
        """执行单阶段老化 Cypher 并读取变更数量。"""
        result = await session.run(query, params)
        record = await result.single()
        return int(record["changed"]) if record else 0

    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体及其关联关系。

        Args:
            entity_id: 实体 ID。

        Returns:
            是否成功删除。
        """
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            result = await session.run(
                "MATCH (e:KGEntity {id: $id}) DETACH DELETE e RETURN count(e) AS deleted",
                id=entity_id,
            )
            record = await result.single()
        deleted = record["deleted"] if record else 0
        return deleted > 0

    async def soft_delete_entity(self, entity_id: str) -> bool:
        """软删除实体（标记 deleted_at）。

        Args:
            entity_id: 实体 ID。

        Returns:
            是否成功标记。
        """
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            result = await session.run(
                """
                MATCH (e:KGEntity {id: $id})
                SET e.deleted_at = timestamp(), e.status = 'deleted'
                RETURN count(e) AS updated
                """,
                id=entity_id,
            )
            record = await result.single()
        updated = record["updated"] if record else 0
        return updated > 0

    async def run_cypher(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        """执行任意 Cypher 查询（用于版本控制快照/回滚等）。

        Args:
            query: Cypher 查询语句。
            params: 查询参数。

        Returns:
            查询结果记录列表。
        """
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            # 参数以 dict 形式传入，避免 params 含 query 键时与位置参数冲突
            result = await session.run(query, params or {})
            return await result.fetch(10000)

    def _record_to_entity(self, node: Any) -> KGEntity:
        """将 Neo4j 节点记录转为 KGEntity。

        Args:
            node: Neo4j 节点对象。

        Returns:
            KGEntity 实例。
        """
        props = dict(node)
        return KGEntity(
            id=props.get("id", ""),
            name=props.get("name", ""),
            type=props.get("type", "Concept"),
            category=props.get("category", ""),
            description=props.get("description", ""),
            properties={},
            confidence=float(props.get("confidence", 0.9)),
            source_text_unit_id=props.get("source_text_unit_id", ""),
            workspace_id=props.get("workspace_id", ""),
        )


