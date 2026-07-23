"""RetrievalPipeline 和 KnowledgeGraphBuilder 主入口。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.ingestion.chunker import MultiGranularityChunker
from app.knowledge_layer.ingestion.claims_extractor import ClaimsExtractor
from app.knowledge_layer.ingestion.document_loader import DocumentLoader
from app.knowledge_layer.ingestion.entity_embedder import EntityEmbedder
from app.knowledge_layer.ingestion.entity_extractor import EntityExtractor
from app.knowledge_layer.ingestion.entity_resolver import EntityResolver
from app.knowledge_layer.ingestion.kg_versioning import KnowledgeGraphVersioning
from app.knowledge_layer.ingestion.relation_extractor import RelationExtractor
from app.knowledge_layer.ingestion.text_unit_builder import TextUnitBuilder
from app.knowledge_layer.models import (
    BuildStats,
    RetrievalContext,
    ScoredDoc,
)
from app.knowledge_layer.retrieval.compressor import Compressor
from app.knowledge_layer.retrieval.enricher import QueryEnricher
from app.knowledge_layer.retrieval.fusion import RRFFusion
from app.knowledge_layer.retrieval.global_search import GlobalSearch
from app.knowledge_layer.retrieval.intent_router import IntentRouter
from app.knowledge_layer.retrieval.local_search import LocalSearch
from app.knowledge_layer.retrieval.reranker import ReRanker
from app.knowledge_layer.retrieval.rewriter import QueryRewriter
from app.knowledge_layer.vector_store import PGVectorStore

logger = get_logger("prd2tsd.knowledge.pipeline")


class KnowledgeGraphBuilder:
    """知识图谱构建器 — 文档→知识图谱的完整生命周期。"""

    def __init__(
        self,
        graph_store: Neo4jGraphStore | None = None,
        vector_store: PGVectorStore | None = None,
        entity_extractor_model: str | None = None,
        relation_extractor_model: str | None = None,
    ) -> None:
        """初始化构建器。

        Args:
            graph_store: Neo4j 图存储。
            vector_store: PGVector 向量存储。
            entity_extractor_model: 实体提取 LLM 模型名。
            relation_extractor_model: 关系提取 LLM 模型名。
        """
        self.graph_store = graph_store or Neo4jGraphStore()
        self.vector_store = vector_store or PGVectorStore()
        self.doc_loader = DocumentLoader()
        self.chunker = MultiGranularityChunker(
            sentence_max_words=kn_config.sentence_max_words,
            paragraph_max_words=kn_config.paragraph_max_words,
        )
        self.entity_extractor = EntityExtractor(model=entity_extractor_model)
        self.relation_extractor = RelationExtractor(model=relation_extractor_model)
        self.entity_resolver = EntityResolver()
        self.claims_extractor = ClaimsExtractor(model=entity_extractor_model)
        self.entity_embedder = EntityEmbedder()
        self.text_unit_builder = TextUnitBuilder()
        self.versioning = KnowledgeGraphVersioning(graph_store=self.graph_store)

    async def build_from_document(
        self,
        file_path: str,
        workspace_id: str = "",
    ) -> BuildStats:
        """从文档构建知识图谱。

        Args:
            file_path: 文档路径。
            workspace_id: 工作空间 ID。

        Returns:
            构建统计。
        """
        logger.info("开始从文档构建知识图谱: %s", file_path)

        # 1. 加载文档
        text = self.doc_loader.load(file_path)

        # 2. 多粒度分块（用段落级）
        chunks = self.chunker.chunk(text, level="paragraph")

        # 3. 实体提取
        entities = await self.entity_extractor.extract(chunks)

        # 4. 实体消歧
        existing_entities = await self.graph_store.get_all_entities(workspace_id)
        resolved_entities = await self.entity_resolver.resolve_batch(entities, existing_entities)
        # 标记 workspace_id
        for entity in resolved_entities:
            if not entity.workspace_id:
                entity.workspace_id = workspace_id

        # 5. 关系提取
        relations = await self.relation_extractor.extract(resolved_entities, chunks)
        for relation in relations:
            if not relation.workspace_id:
                relation.workspace_id = workspace_id

        # 6. 构建 TextUnit
        text_units = self.text_unit_builder.build(
            chunks=chunks,
            entities=resolved_entities,
            relations=relations,
            workspace_id=workspace_id,
        )

        # 7. Claims 提取
        claims = await self.claims_extractor.extract(text_units, resolved_entities)
        for claim in claims:
            if not claim.workspace_id:
                claim.workspace_id = workspace_id

        # 8. 实体 Embedding
        for entity in resolved_entities:
            related_units = [tu for tu in text_units if entity.id in tu.entities]
            related_claims = [c for c in claims if c.subject_entity_id == entity.id]
            entity.embedding = self.entity_embedder.embed_entity(entity, related_units, related_claims)

        # 9. TextUnit Embedding
        tu_embeddings = self.entity_embedder.embed_text_units(text_units)

        # 10. Claims Embedding
        claim_embeddings = self.entity_embedder.embed_claims(claims)

        # 11. 写入 Neo4j
        await self.graph_store.upsert_entities(resolved_entities)
        await self.graph_store.upsert_relations(relations)
        for tu in text_units:
            await self.graph_store.upsert_text_unit(tu)
        await self.graph_store.upsert_claims(claims)

        # 12. 写入 PGVector
        await self.vector_store.ensure_extensions()
        for tu, emb in zip(text_units, tu_embeddings, strict=False):
            await self.vector_store.upsert_text_unit(tu, emb)
        for entity in resolved_entities:
            if entity.embedding:
                await self.vector_store.upsert_entity_embedding(
                    entity_id=entity.id,
                    name=entity.name,
                    entity_type=entity.type,
                    description=entity.description,
                    embedding=entity.embedding,
                    workspace_id=workspace_id,
                )
        for claim, emb in zip(claims, claim_embeddings, strict=False):
            await self.vector_store.upsert_claim_embedding(claim, emb)

        # 13. 创建版本快照
        version_id = await self.versioning.create_snapshot(
            name=f"build_from_{file_path.split('/')[-1]}",
            workspace_id=workspace_id,
        )

        stats = BuildStats(
            entities=len(resolved_entities),
            relations=len(relations),
            text_units=len(text_units),
            claims=len(claims),
            file_path=file_path,
            workspace_id=workspace_id,
            version_id=version_id,
        )

        logger.info(
            "知识图谱构建完成: entities=%d, relations=%d, text_units=%d, claims=%d",
            stats.entities,
            stats.relations,
            stats.text_units,
            stats.claims,
        )
        return stats


class RetrievalPipeline:
    """多路检索主入口。"""

    def __init__(
        self,
        graph_store: Neo4jGraphStore | None = None,
        vector_store: PGVectorStore | None = None,
    ) -> None:
        """初始化检索管线。

        Args:
            graph_store: Neo4j 图存储。
            vector_store: PGVector 向量存储。
        """
        self.graph_store = graph_store or Neo4jGraphStore()
        self.vector_store = vector_store or PGVectorStore()
        self.intent_router = IntentRouter()
        self.rewriter = QueryRewriter()
        self.enricher = QueryEnricher(graph_store=self.graph_store)
        self.local_search = LocalSearch(graph_store=self.graph_store)
        self.global_search = GlobalSearch(graph_store=self.graph_store)
        self.fusion = RRFFusion()
        self.reranker = ReRanker()
        self.compressor = Compressor()

    async def retrieve(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        workspace_id: str = "",
    ) -> RetrievalContext:
        """多路检索主入口。

        Args:
            query: 用户查询文本。
            mode: 检索模式（local / global / hybrid）。
            top_k: 返回结果数。
            workspace_id: 工作空间 ID（租户隔离）。

        Returns:
            包含检索结果和上下文的 RetrievalContext。
        """
        logger.info("检索开始: query=%s, mode=%s, top_k=%d", query, mode, top_k)

        # 1. 意图路由（如未指定模式）
        detected_mode = self.intent_router.route(query) if mode == "hybrid" else mode

        # 2. 查询重写
        sub_queries = await self.rewriter.rewrite(query)

        # 3. 查询丰富
        enriched_query, matched_entity_ids = await self.enricher.enrich(query, workspace_id)

        # 4. 多路检索
        all_results: list[ScoredDoc] = []
        local_docs: list[ScoredDoc] = []
        global_docs: list[ScoredDoc] = []

        if detected_mode in ("local", "hybrid"):
            for sq in sub_queries[:3]:
                sq_docs = await self.local_search.search_as_docs(sq, workspace_id, top_k)
                local_docs.extend(sq_docs)
            # 去重
            seen_ids: set[str] = set()
            unique_local: list[ScoredDoc] = []
            for doc in local_docs:
                if doc.id not in seen_ids:
                    seen_ids.add(doc.id)
                    unique_local.append(doc)
            all_results.extend(unique_local)

        if detected_mode in ("global", "hybrid"):
            global_result = await self.global_search.search(query, workspace_id)
            global_docs = await self.global_search.search_as_docs(query, workspace_id)
            all_results.extend(global_docs)

        # 5. RRF 融合（hybrid 模式）
        if detected_mode == "hybrid" and local_docs and global_docs:
            all_results = self.fusion.fuse(local_docs, global_docs)

        # 6. 重排
        reranked = self.reranker.rerank(query, all_results, top_k)

        # 7. 压缩
        compressed = self.compressor.compress(reranked)

        # 8. 组装结果
        context = RetrievalContext(
            query=query,
            mode=detected_mode,
            results=compressed,
            text_unit_evidence=[],
            community_summary=global_result.answer if detected_mode in ("global", "hybrid") else "",
        )

        logger.info(
            "检索完成: mode=%s, results=%d",
            detected_mode,
            len(compressed),
        )
        return context
