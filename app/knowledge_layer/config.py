"""知识层配置 — Neo4j / PGVector / Embedding 连接参数。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class KnowledgeLayerConfig:
    """知识层配置。"""

    # ── Neo4j ──
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""
    neo4j_database: str = ""

    # ── PGVector ──
    pgvector_connection_string: str = ""
    pgvector_table_name: str = ""

    # ── Embedding ──
    embedding_model_name: str = "BAAI/bge-large-zh-v1.5"
    embedding_dimension: int = 1024
    embedding_device: str = "cpu"

    # ── Chunking ──
    sentence_max_words: int = 50
    paragraph_max_words: int = 500

    # ── Retrieval ──
    local_top_k: int = 10
    global_top_k: int = 5
    hybrid_top_k: int = 10
    rrf_k: int = 60
    max_compress_tokens: int = 4000

    # ── Aging ──
    downgrade_days: int = 90
    archive_days: int = 180
    soft_delete_days: int = 365

    # ── Entity Resolution ──
    semantic_similarity_threshold: float = 0.85

    def __post_init__(self) -> None:
        """未显式设置时从 settings 读取默认值。"""
        if not self.neo4j_uri:
            self.neo4j_uri = settings.NEO4J_URI
        if not self.neo4j_user:
            self.neo4j_user = settings.NEO4J_USER
        if not self.neo4j_password:
            self.neo4j_password = settings.NEO4J_PASSWORD
        if not self.neo4j_database:
            self.neo4j_database = settings.NEO4J_DATABASE
        if not self.pgvector_connection_string:
            # 复用同一数据库，启用 pgvector 扩展
            self.pgvector_connection_string = settings.DATABASE_URL.replace(
                "+asyncpg", ""
            ).replace(
                "postgresql://", "postgresql+asyncpg://"
            )


# 全局单例
kn_config = KnowledgeLayerConfig()
