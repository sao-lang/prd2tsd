"""PGVector 向量存储封装 — Chunk / Entity / Claim Embedding 的向量读写。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import Chunk, ScoredDoc

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
        return connector.get_session()

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
                document_id VARCHAR(64) DEFAULT '',
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
        # Block F: Claims Embedding 表
        await session.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS claim_embeddings (
                id VARCHAR(64) PRIMARY KEY,
                subject VARCHAR(256) NOT NULL,
                claim_type VARCHAR(32) NOT NULL,
                content TEXT NOT NULL,
                object TEXT DEFAULT '',
                embedding vector({self._dimension}),
                source_text_unit_id VARCHAR(64) DEFAULT '',
                workspace_id VARCHAR(64) DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
            )
        )
        await session.commit()
        logger.info("PGVector 表已就绪")

    async def upsert_chunk(
        self,
        chunk: Chunk,
        embedding: list[float] | None = None,
        document_id: str = "",
        workspace_id: str = "",
    ) -> None:
        """写入 Chunk 向量。

        Args:
            chunk: Chunk 对象。
            embedding: 向量。为 None 时不写入向量。
            document_id: 所属文档 ID（文档语义搜索关联用）。
            workspace_id: 工作空间 ID（租户隔离）。
        """
        session = await self._get_session()
        vec_str = json.dumps(embedding) if embedding else None
        await session.execute(
            text(
                """
            INSERT INTO text_unit_embeddings (id, text, embedding, section_path, entity_ids, workspace_id, document_id)
            VALUES (:id, :text, :embedding::vector, :section_path, :entity_ids, :workspace_id, :document_id)
            ON CONFLICT (id) DO UPDATE SET
                text = EXCLUDED.text,
                embedding = EXCLUDED.embedding,
                section_path = EXCLUDED.section_path,
                entity_ids = EXCLUDED.entity_ids,
                document_id = EXCLUDED.document_id,
                workspace_id = EXCLUDED.workspace_id
            """
            ),
            {
                "id": chunk.id,
                "text": chunk.text,
                "embedding": vec_str,
                "section_path": chunk.section_path or "",
                "entity_ids": "[]",
                "workspace_id": workspace_id,
                "document_id": document_id,
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
                embedding = EXCLUDED.embedding,
                workspace_id = EXCLUDED.workspace_id
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
            table: 表名（text_unit_embeddings / entity_embeddings）。
            top_k: 返回数量。
            workspace_id: 工作空间 ID。

        Returns:
            排序后的检索结果列表。
        """
        _allowed_tables = {"text_unit_embeddings", "entity_embeddings", "claim_embeddings"}
        if table not in _allowed_tables:
            raise ValueError(f"不允许查询表: {table}")

        session = await self._get_session()
        vec_str = json.dumps(embedding)
        select_columns = {
            "text_unit_embeddings": "id, text AS text_content, document_id",
            "entity_embeddings": (
                "id, COALESCE(NULLIF(description, ''), name) AS text_content, "
                "name, entity_type"
            ),
            "claim_embeddings": "id, content AS text_content, subject, claim_type",
        }
        query = text(
            f"""
            SELECT {select_columns[table]},
                   1 - (embedding <=> :vec::vector) AS similarity
            FROM {table}
            WHERE embedding IS NOT NULL
              AND (:workspace_id = '' OR workspace_id = :workspace_id)
            ORDER BY similarity DESC NULLS LAST
            LIMIT :top_k
            """
        )
        params: dict[str, Any] = {
            "vec": vec_str,
            "workspace_id": workspace_id,
            "top_k": top_k,
        }
        result = await session.execute(query, params)
        rows = result.fetchall()

        docs: list[ScoredDoc] = []
        for row in rows:
            row_dict = dict(row._mapping)
            metadata: dict[str, Any] = {"table": table}
            if table == "text_unit_embeddings":
                metadata["document_id"] = row_dict.get("document_id", "")
            elif table == "entity_embeddings":
                metadata.update(
                    name=row_dict.get("name", ""),
                    entity_type=row_dict.get("entity_type", ""),
                )
            elif table == "claim_embeddings":
                metadata.update(
                    subject=row_dict.get("subject", ""),
                    claim_type=row_dict.get("claim_type", ""),
                )
            docs.append(
                ScoredDoc(
                    id=row_dict.get("id", ""),
                    text=str(row_dict.get("text_content", "")),
                    score=float(row_dict.get("similarity", 0.0)),
                    source="vector",
                    metadata=metadata,
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
        _allowed_tables = {"text_unit_embeddings", "entity_embeddings", "claim_embeddings"}
        if table not in _allowed_tables:
            raise ValueError(f"不允许删除表: {table}")

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
        _allowed_tables = {"text_unit_embeddings", "entity_embeddings", "claim_embeddings"}
        if table not in _allowed_tables:
            raise ValueError(f"不允许统计表: {table}")

        session = await self._get_session()
        result = await session.execute(
            text(f"SELECT COUNT(*) AS cnt FROM {table} WHERE (:workspace_id = '' OR workspace_id = :workspace_id)"),
            {"workspace_id": workspace_id},
        )
        row = result.one()
        return int(row[0])

    # ════════════════════════════════════════════
    # Block F: Claims 操作
    # ════════════════════════════════════════════

    async def upsert_claim(
        self,
        claim: Any,
        embedding: list[float] | None = None,
    ) -> None:
        """写入 Claim Embedding。

        Args:
            claim: Claim 模型实例。
            embedding: 向量。
        """
        session = await self._get_session()
        vec_str = json.dumps(embedding) if embedding else None
        await session.execute(
            text(
                """
            INSERT INTO claim_embeddings
            (id, subject, claim_type, content, object, embedding, source_text_unit_id, workspace_id)
            VALUES
            (:id, :subject, :claim_type, :content, :object, :embedding::vector, :source_text_unit_id, :workspace_id)
            ON CONFLICT (id) DO UPDATE SET
                subject = EXCLUDED.subject,
                claim_type = EXCLUDED.claim_type,
                content = EXCLUDED.content,
                object = EXCLUDED.object,
                embedding = EXCLUDED.embedding,
                source_text_unit_id = EXCLUDED.source_text_unit_id,
                workspace_id = EXCLUDED.workspace_id
            """
            ),
            {
                "id": claim.id,
                "subject": claim.subject,
                "claim_type": claim.claim_type,
                "content": claim.content,
                "object": claim.object or "",
                "embedding": vec_str,
                "source_text_unit_id": claim.source_text_unit_id or "",
                "workspace_id": claim.workspace_id or "",
            },
        )
        await session.commit()

    async def search_claims(
        self,
        query: str,
        top_k: int = 5,
        workspace_id: str = "",
    ) -> list[Any]:
        """语义搜索 Claims。

        Args:
            query: 查询文本。
            top_k: 返回数量。
            workspace_id: 工作空间 ID。

        Returns:
            Claim 对象列表。
        """
        from app.knowledge_layer.models import Claim

        session = await self._get_session()
        where_clause = ""
        if workspace_id:
            where_clause = f"WHERE workspace_id = '{workspace_id}'"
        query_sql = text(
            f"""
            SELECT id, subject, claim_type, content, object, source_text_unit_id, workspace_id
            FROM claim_embeddings
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {top_k}
            """
        )
        result = await session.execute(query_sql)
        rows = result.fetchall()

        claims: list[Claim] = []
        for row in rows:
            row_dict = dict(row._mapping)
            claims.append(
                Claim(
                    id=row_dict.get("id", ""),
                    subject=row_dict.get("subject", ""),
                    claim_type=row_dict.get("claim_type", "specification"),
                    content=row_dict.get("content", ""),
                    object=row_dict.get("object", ""),
                    source_text_unit_id=row_dict.get("source_text_unit_id", ""),
                    workspace_id=row_dict.get("workspace_id", ""),
                )
            )
        return claims
