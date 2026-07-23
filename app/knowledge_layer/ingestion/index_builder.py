"""LlamaIndex PropertyGraphIndex 构建。"""

from __future__ import annotations

from typing import Any

from llama_index.core import Document, PropertyGraphIndex, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.vector_stores.postgres import PGVectorStore

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import TextUnit

logger = get_logger("prd2tsd.knowledge.index_builder")


class IndexBuilder:
    """LlamaIndex PropertyGraphIndex 构建器。"""

    def __init__(self) -> None:
        """初始化索引构建器。"""
        self._embed_model: Any = None
        self._graph_store: Any = None
        self._vector_store: Any = None

    def _init_llama_index_stores(self) -> None:
        """初始化 LlamaIndex 存储后端。"""
        if self._embed_model is None:
            self._embed_model = HuggingFaceEmbedding(
                model_name=kn_config.embedding_model_name,
                device=kn_config.embedding_device,
            )
            Settings.embed_model = self._embed_model

        if self._graph_store is None:
            self._graph_store = Neo4jGraphStore(
                url=kn_config.neo4j_uri,
                username=kn_config.neo4j_user,
                password=kn_config.neo4j_password,
                database=kn_config.neo4j_database,
            )

        if self._vector_store is None:
            self._vector_store = PGVectorStore.from_params(
                connection_string=kn_config.pgvector_connection_string,
                table_name="text_unit_embeddings",
                embed_dim=kn_config.embedding_dimension,
            )

    async def build_from_text_units(
        self,
        text_units: list[TextUnit],
    ) -> PropertyGraphIndex:
        """从 TextUnit 构建 PropertyGraphIndex。

        Args:
            text_units: TextUnit 列表。

        Returns:
            构建好的 PropertyGraphIndex。
        """
        self._init_llama_index_stores()

        documents = [
            Document(
                text=tu.text,
                metadata={
                    "id": tu.id,
                    "section_path": tu.section_path,
                    "entities": ",".join(tu.entities),
                },
            )
            for tu in text_units
        ]

        if not documents:
            logger.warning("无可构建索引的文档")
            return PropertyGraphIndex.from_documents([], embed_model=self._embed_model)

        index = PropertyGraphIndex.from_documents(
            documents,
            embed_model=self._embed_model,
            graph_store=self._graph_store,
            vector_store=self._vector_store,
            show_progress=True,
        )
        logger.info("PropertyGraphIndex 构建完成: %d docs", len(documents))
        return index
