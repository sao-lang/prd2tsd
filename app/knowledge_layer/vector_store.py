"""PGVector 向量存储封装 — TextUnit / Entity Embedding 的向量读写。"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import Claim, ScoredDoc, TextUnit

logger = get_logger("prd2tsd.knowledge.vector_store")


class PGVectorStore:
    """PGVector 向量存储封装。"""

    def __init__(self, session: AsyncSession | None = None) -> None:
        """初始化 PGVector 存储。

        Args:
            session: SQLAlchemy 异步会话。为 None 时从 ConnectionManager 获取。
        """
        self._session = session
        self._dimension = kn_config.embedding_dimension

    async def _get_session(self) -> AsyncSession:
        """获取数据库会话。

        Returns:
            AsyncSession 实例。
        """
        if self._session is not None:
            return self._session
        connector = connection_manager.get("postgres")
        return connector.get_session()  # type: ignore[attr-defined,no-any-return]

    async def ensure_extensions(self) -> None:
        """确保 pgvector 扩展已启用且表已创建。"""
        session = await self._get_session()
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS text_unit_embeddings (
                id VARCHAR(64) PRIMARY KEY,
                text TEXT NOT NULL,
                embedding vector({self._dimension}),
                section_path VARCHAR(512) DEFAULT '',
                entity_ids TEXT DEFAULT '[]',
                workspace_id VARCHAR(64) DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
            )
        )
        await session.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS entity_embeddings (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(256) NOT NULL,
                entity_type VARCHAR(64) DEFAULT '',
                description TEXT DEFAULT '',
                embedding vector({self._dimension}),
                workspace_id VARCHAR(64) DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
            )
        )
        await session.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS claim_embeddings (
                id VARCHAR(64) PRIMARY KEY,
                claim_type VARCHAR(64) DEFAULT '',
                content TEXT NOT NULL,
                subject_entity_id VARCHAR(64) DEFAULT '',
                embedding vector({self._dimension}),
                workspace_id VARCHAR(64) DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
            )
        )
        await session.commit()
        logger.info("PGVector 表已就绪")

    async def upsert_text_unit(
        self,
        text_unit: TextUnit,
        embedding: list[float] | None = None,
    ) -> None:
        """写入 TextUnit 向量。

        Args:
            text_unit: TextUnit 对象。
            embedding: 向量。为 None 时不写入向量。
        """
        session = await self._get_session()
        vec_str = json.dumps(embedding) if embedding else None
        entity_ids = json.dumps(text_unit.entities, ensure_ascii=False)
        await session.execute(
            text(
                """
            INSERT INTO text_unit_embeddings (id, text, embedding, section_path, entity_ids, workspace_id)
            VALUES (:id, :text, :embedding::vector, :section_path, :entity_ids, :workspace_id)
            ON CONFLICT (id) DO UPDATE SET
                text = EXCLUDED.text,
                embedding = EXCLUDED.embedding,
                section_path = EXCLUDED.section_path,
                entity_ids = EXCLUDED.entity_ids
            """
            ),
            {
                "id": text_unit.id,
                "text": text_unit.text,
                "embedding": vec_str,
                "section_path": text_unit.section_path,
                "entity_ids": entity_ids,
                "workspace_id": text_unit.workspace_id,
            },
        )
        await session.commit()

    async def upsert_entity_embedding(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        description: str,
        embedding: list[float],
        workspace_id: str = "",
    ) -> None:
        """写入实体 Embedding。

        Args:
            entity_id: 实体 ID。
            name: 实体名称。
            entity_type: 实体类型。
            description: 实体描述。
            embedding: 向量。
            workspace_id: 工作空间 ID。
        """
        session = await self._get_session()
        vec_str = json.dumps(embedding)
        await session.execute(
            text(
                """
            INSERT INTO entity_embeddings (id, name, entity_type, description, embedding, workspace_id)
            VALUES (:id, :name, :entity_type, :description, :embedding::vector, :workspace_id)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                entity_type = EXCLUDED.entity_type,
                description = EXCLUDED.description,
                embedding = EXCLUDED.embedding
            """
            ),
            {
                "id": entity_id,
                "name": name,
                "entity_type": entity_type,
                "description": description,
                "embedding": vec_str,
                "workspace_id": workspace_id,
            },
        )
        await session.commit()

    async def upsert_claim_embedding(
        self,
        claim: Claim,
        embedding: list[float],
    ) -> None:
        """写入 Claim 向量。

        Args:
            claim: Claim 对象。
            embedding: 向量。
        """
        session = await self._get_session()
        vec_str = json.dumps(embedding)
        await session.execute(
            text(
                """
            INSERT INTO claim_embeddings (id, claim_type, content, subject_entity_id, embedding, workspace_id)
            VALUES (:id, :claim_type, :content, :subject_entity_id, :embedding::vector, :workspace_id)
            ON CONFLICT (id) DO UPDATE SET
                claim_type = EXCLUDED.claim_type,
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding
            """
            ),
            {
                "id": claim.id,
                "claim_type": claim.claim_type,
                "content": claim.content,
                "subject_entity_id": claim.subject_entity_id,
                "embedding": vec_str,
                "workspace_id": claim.workspace_id,
            },
        )
        await session.commit()

    async def similarity_search(
        self,
        embedding: list[float],
        table: str = "text_unit_embeddings",
        top_k: int = 10,
        workspace_id: str = "",
    ) -> list[ScoredDoc]:
        """向量相似度搜索。

        Args:
            embedding: 查询向量。
            table: 表名（text_unit_embeddings / entity_embeddings / claim_embeddings）。
            top_k: 返回数量。
            workspace_id: 工作空间 ID。

        Returns:
            排序后的检索结果列表。
        """
        session = await self._get_session()
        vec_str = json.dumps(embedding)
        where_clause = ""
        if workspace_id:
            where_clause = f"WHERE workspace_id = '{workspace_id}'"
        query = text(
            f"""
            SELECT id, text, content, name, description,
                   1 - (embedding <=> '{vec_str}'::vector) AS similarity
            FROM {table}
            {where_clause}
            ORDER BY similarity DESC
            LIMIT {top_k}
            """
        )
        result = await session.execute(query)
        rows = result.fetchall()

        docs: list[ScoredDoc] = []
        for row in rows:
            row_dict = dict(row._mapping)
            text_content = (
                row_dict.get("text")
                or row_dict.get("content")
                or row_dict.get("description")
                or row_dict.get("name", "")
            )
            docs.append(
                ScoredDoc(
                    id=row_dict.get("id", ""),
                    text=str(text_content),
                    score=float(row_dict.get("similarity", 0.0)),
                    source="vector",
                    metadata={"table": table},
                )
            )
        return docs

    async def delete_by_id(self, table: str, entity_id: str) -> bool:
        """按 ID 删除向量记录。

        Args:
            table: 表名。
            entity_id: 记录 ID。

        Returns:
            是否成功删除。
        """
        session = await self._get_session()
        result = await session.execute(
            text(f"DELETE FROM {table} WHERE id = :id"),
            {"id": entity_id},
        )
        await session.commit()
        count = getattr(result, "rowcount", 0)
        return (count or 0) > 0

    async def count_records(self, table: str, workspace_id: str = "") -> int:
        """统计记录数。

        Args:
            table: 表名。
            workspace_id: 工作空间 ID。

        Returns:
            记录数量。
        """
        session = await self._get_session()
        where = f"WHERE workspace_id = '{workspace_id}'" if workspace_id else ""
        result = await session.execute(
            text(f"SELECT COUNT(*) AS cnt FROM {table} {where}")
        )
        row = result.one()
        return int(row[0])
