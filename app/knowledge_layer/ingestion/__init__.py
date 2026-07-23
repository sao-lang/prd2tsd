"""Ingestion — 文档加载 → 分块 → 实体/关系提取 → 存储。"""

from __future__ import annotations

from app.knowledge_layer.ingestion.chunker import MultiGranularityChunker
from app.knowledge_layer.ingestion.claims_extractor import ClaimsExtractor
from app.knowledge_layer.ingestion.document_loader import DocumentLoader
from app.knowledge_layer.ingestion.entity_embedder import EntityEmbedder
from app.knowledge_layer.ingestion.entity_extractor import EntityExtractor
from app.knowledge_layer.ingestion.entity_resolver import EntityResolver
from app.knowledge_layer.ingestion.index_builder import IndexBuilder
from app.knowledge_layer.ingestion.kg_versioning import KnowledgeGraphVersioning
from app.knowledge_layer.ingestion.knowledge_aging import KnowledgeAgingPolicy
from app.knowledge_layer.ingestion.relation_extractor import RelationExtractor
from app.knowledge_layer.ingestion.text_unit_builder import TextUnitBuilder
from app.knowledge_layer.models import Chunk

__all__ = [
    "DocumentLoader",
    "MultiGranularityChunker",
    "Chunk",
    "EntityExtractor",
    "RelationExtractor",
    "EntityResolver",
    "ClaimsExtractor",
    "EntityEmbedder",
    "TextUnitBuilder",
    "KnowledgeAgingPolicy",
    "KnowledgeGraphVersioning",
    "IndexBuilder",
]
