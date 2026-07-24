"""Neo4j 图存储封装 — 实体的 CRUD 操作。"""

from __future__ import annotations

import uuid
from typing import Any

from neo4j import AsyncDriver

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import KGEntity

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
        return connector.get_driver()  # type: ignore[attr-defined,no-any-return]

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
                SET e.name = $name,
                    e.type = $type,
                    e.category = $category,
                    e.description = $description,
                    e.properties = $properties,
                    e.confidence = $confidence,
                    e.workspace_id = $workspace_id,
                    e.source_text_unit_id = $source_text_unit_id,
                    e.updated_at = timestamp()
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

    async def upsert_entities(self, entities: list[KGEntity]) -> list[str]:
        """批量创建或更新实体。

        Args:
            entities: 实体列表。

        Returns:
            实体 ID 列表。
        """
        return [await self.upsert_entity(e) for e in entities]

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
            result = await session.run(query, **params)
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
        """
        params: dict[str, Any] = {"query": query, "limit": limit}
        if workspace_id:
            cypher += " AND e.workspace_id = $workspace_id"
        cypher += " RETURN e LIMIT $limit"
        async with driver.session(database=self._database) as session:
            result = await session.run(cypher, **params)
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
            result = await session.run(cypher, **params)
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
            cypher += " WHERE e.workspace_id = $workspace_id"
            params["workspace_id"] = workspace_id
        cypher += " RETURN e"
        async with driver.session(database=self._database) as session:
            result = await session.run(cypher, **params)
            records = await result.fetch(10000)
        return [self._record_to_entity(r["e"]) for r in records]

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
            result = await session.run(query, **(params or {}))
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


