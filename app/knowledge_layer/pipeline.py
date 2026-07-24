"""RetrievalPipeline 和 KnowledgeGraphBuilder 主入口。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.ingestion.chunker import MultiGranularityChunker
from app.knowledge_layer.ingestion.document_loader import DocumentLoader
from app.knowledge_layer.ingestion.entity_embedder import EntityEmbedder
from app.knowledge_layer.ingestion.entity_extractor import EntityExtractor
from app.knowledge_layer.ingestion.entity_resolver import EntityResolver
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
from app.knowledge_layer.retrieval.reflection import ReflectionJudge
from app.knowledge_layer.retrieval.reranker import ReRanker
from app.knowledge_layer.retrieval.rewriter import QueryRewriter
from app.knowledge_layer.vector_store import PGVectorStore

logger = get_logger("prd2tsd.knowledge.pipeline")


class KnowledgeGraphBuilder:
    """知识图谱构建器 — 文档→实体索引。"""

    def __init__(
        self,
        graph_store: Neo4jGraphStore | None = None,
        vector_store: PGVectorStore | None = None,
        entity_extractor_model: str | None = None,
    ) -> None:
        """初始化构建器。

        Args:
            graph_store: Neo4j 图存储。
            vector_store: PGVector 向量存储。
            entity_extractor_model: 实体提取 LLM 模型名。
        """
        self.graph_store = graph_store or Neo4jGraphStore()
        self.vector_store = vector_store or PGVectorStore()
        self.doc_loader = DocumentLoader()
        self.chunker = MultiGranularityChunker(
            sentence_max_words=kn_config.sentence_max_words,
            paragraph_max_words=kn_config.paragraph_max_words,
        )
        self.entity_extractor = EntityExtractor(model=entity_extractor_model)
        self.entity_resolver = EntityResolver()
        self.entity_embedder = EntityEmbedder()

    async def build_from_document(
        self,
        file_path: str,
        workspace_id: str = "",
    ) -> BuildStats:
        """从文档构建实体索引。

        Args:
            file_path: 文档路径。
            workspace_id: 工作空间 ID。

        Returns:
            构建统计。
        """
        logger.info("开始构建实体索引: %s", file_path)

        # 1. 加载文档
        text = self.doc_loader.load(file_path)

        # 2. 多粒度分块（用段落级）
        chunks = self.chunker.chunk(text, level="paragraph")

        # 3. 实体提取
        entities = await self.entity_extractor.extract(chunks)

        # 4. 实体消歧
        existing_entities = await self.graph_store.get_all_entities(workspace_id)
        resolved_entities = await self.entity_resolver.resolve_batch(entities, existing_entities)
        for entity in resolved_entities:
            if not entity.workspace_id:
                entity.workspace_id = workspace_id

        # 5. 实体 Embedding（双源：名称+描述）— 通过 Gateway 调用
        for entity in resolved_entities:
            entity.embedding = await self.entity_embedder.embed_entity(entity)

        # 6. 写入 Neo4j（仅实体）
        await self.graph_store.upsert_entities(resolved_entities)

        # 7. 写入 PGVector
        await self.vector_store.ensure_extensions()
        for chunk in chunks:
            chunk_emb = await self.entity_embedder.embed_text(chunk.text)
            await self.vector_store.upsert_chunk(chunk, chunk_emb)
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

        stats = BuildStats(
            entities=len(resolved_entities),
            chunks=len(chunks),
            file_path=file_path,
            workspace_id=workspace_id,
        )

        logger.info(
            "实体索引构建完成: entities=%d, chunks=%d",
            stats.entities,
            stats.chunks,
        )
        return stats

    async def build_from_text(
        self,
        text: str,
        source_name: str = "",
        workspace_id: str = "",
    ) -> BuildStats:
        """从文本内容构建实体索引（无需文件路径，适用于 Web 抓取内容）。

        Args:
            text: 文本内容。
            source_name: 来源名称（如 URL 或文档标题）。
            workspace_id: 工作空间 ID。

        Returns:
            构建统计。
        """
        logger.info("开始从文本构建实体索引: source=%s", source_name or "unknown")

        # 1. 多粒度分块
        chunks = self.chunker.chunk(text, level="paragraph")

        # 2. 实体提取
        entities = await self.entity_extractor.extract(chunks)

        # 3. 实体消歧
        existing_entities = await self.graph_store.get_all_entities(workspace_id)
        resolved_entities = await self.entity_resolver.resolve_batch(entities, existing_entities)
        for entity in resolved_entities:
            if not entity.workspace_id:
                entity.workspace_id = workspace_id
            if source_name and not entity.properties.get("source"):
                entity.properties["source"] = source_name

        # 4. 实体 Embedding — 通过 Gateway 调用
        for entity in resolved_entities:
            entity.embedding = await self.entity_embedder.embed_entity(entity)

        # 5. 写入 Neo4j
        await self.graph_store.upsert_entities(resolved_entities)

        # 6. 写入 PGVector
        await self.vector_store.ensure_extensions()
        for chunk in chunks:
            chunk_emb = await self.entity_embedder.embed_text(chunk.text)
            await self.vector_store.upsert_chunk(chunk, chunk_emb)
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

        stats = BuildStats(
            entities=len(resolved_entities),
            chunks=len(chunks),
            file_path=source_name,
            workspace_id=workspace_id,
        )

        logger.info(
            "文本实体索引构建完成: source=%s, entities=%d, chunks=%d",
            source_name, stats.entities, stats.chunks,
        )
        return stats


class RetrievalPipeline:
    """多路检索主入口（含反思循环）。"""

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
        self.reflection = ReflectionJudge()
        self.reranker = ReRanker()
        self.compressor = Compressor()
        self.max_reflection_rounds = 2

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

        # 4. ⭐ 带反思循环的检索
        current_query = query
        all_results: list[ScoredDoc] = []

        for round_idx in range(self.max_reflection_rounds + 1):
            # 4a. 多路检索
            local_docs: list[ScoredDoc] = []
            global_docs: list[ScoredDoc] = []
            global_result = None

            if detected_mode in ("local", "hybrid"):
                for sq in sub_queries[:3]:
                    sq_docs = await self.local_search.search_as_docs(sq, workspace_id, top_k)
                    local_docs.extend(sq_docs)
                seen_ids: set[str] = set()
                unique_local: list[ScoredDoc] = []
                for doc in local_docs:
                    if doc.id not in seen_ids:
                        seen_ids.add(doc.id)
                        unique_local.append(doc)
                all_results = unique_local

            if detected_mode in ("global", "hybrid"):
                global_result = await self.global_search.search(current_query, workspace_id)
                global_docs = await self.global_search.search_as_docs(current_query, workspace_id)
                all_results.extend(global_docs)

            # 4b. RRF 融合（hybrid 模式）
            if detected_mode == "hybrid" and local_docs and global_docs:
                all_results = self.fusion.fuse(local_docs, global_docs)

            # 4c. 反思裁判 — 最后一轮不反思
            if round_idx < self.max_reflection_rounds:
                reflection = await self.reflection.judge(current_query, all_results)
                if reflection.judgment == "accept":
                    logger.info("反思第%d轮: accept", round_idx + 1)
                    break
                logger.info(
                    "反思第%d轮: refine — %s → %s",
                    round_idx + 1,
                    reflection.reason,
                    reflection.refined_query,
                )
                current_query = reflection.refined_query or current_query
                sub_queries = [current_query]
            else:
                logger.info("反思达到最大轮数(%d)，采用当前结果", self.max_reflection_rounds)

        # 5. ⭐ E11 搜索引擎回退 — 本地结果不足时自动触发网络搜索
        if len(all_results) < 3:
            try:
                from app.web_indexing.search_fallback import SearchFallback
                fallback = SearchFallback()
                should = await fallback.should_fallback(all_results)
                if should:
                    logger.info("本地检索结果不足(%d)，触发搜索引擎回退", len(all_results))
                    web_results = await fallback.search_and_index(
                        query=query,
                        workspace_id=workspace_id,
                        max_results=top_k,
                        vector_store=self.vector_store,
                    )
                    if web_results:
                        for r in web_results:
                            snippet = r.get("snippet", "") or r.get("title", "")
                            if snippet:
                                all_results.append(ScoredDoc(
                                    id=f"web_{r.get('url', '')[:64]}",
                                    text=snippet,
                                    score=0.5,
                                    source="web_fallback",
                                    metadata={
                                        "url": r.get("url", ""),
                                        "title": r.get("title", ""),
                                        "source": "web_search_fallback",
                                    },
                                ))
                        logger.info("搜索引擎回退追加 %d 条结果", len(web_results))
            except Exception as exc:
                logger.warning("搜索引擎回退失败: %s", exc)

        # 6. 重排
        reranked = self.reranker.rerank(current_query, all_results, top_k)

        # 7. 压缩
        compressed = self.compressor.compress(reranked)

        # 8. 组装结果
        context = RetrievalContext(
            query=query,
            mode=detected_mode,
            results=compressed,
            text_unit_evidence=[],
            community_summary=global_result.answer if detected_mode in ("global", "hybrid") and global_result else "",
        )

        logger.info(
            "检索完成: mode=%s, results=%d",
            detected_mode,
            len(compressed),
        )
        return context
