# 块 B：知识层（数据 + 检索）

> 关联总文档：`prd2tsd.md` §三 Knowledge Layer — 完整设计
>
> **前置条件**：块 A 已完成且全部测试通过。本块使用块 A 提供的 DB Session、Auth 中间件、LLM Gateway、Contract 接口、数据脱敏引擎。

---

## 1. 需求描述

构建知识图谱的完整生命周期：文档上传 → 分块 → 实体/关系提取 → 多路检索。这是系统的数据底座，所有后续 Agent Layer 的分析和规划都依赖本块的检索能力。

### 核心功能列表

1. **文档加载**：支持 .md 文件的多格式加载和解析
2. **多粒度分块**：Sentence / Paragraph / Section 三级分块策略
3. **实体提取**：LLM 驱动的技术实体提取（TechStack / Component / ArchitecturePattern 等）
4. **关系提取**：LLM 驱动的实体间关系提取（depends_on / implements / part_of 等）
5. **实体融合/消歧**（Entity Resolution）：精确匹配 → 别名匹配 → 语义相似度 → 人工确认四级策略
6. **Claims/Covariates 提取**：从 TextUnit 中提取声明性断言（对比/决策/规格/约束/预测）
7. **TextUnit 构建**：Chunk 与 Entity 之间的桥梁层
8. **实体多源融合 Embedding**：名称+描述+TextUnit+Claims 四源加权
9. **Neo4j 存储**：图数据库写入实体 + 关系 + TextUnit + Claims
10. **PGVector 存储**：向量化 TextUnit、Entity Embedding、Claims Embedding
11. **知识图谱版本控制**：快照创建 → 回滚 → 差异查看
12. **知识老化策略**：90天降权 → 180天归档 → 365天软删除
13. **Local Search**：实体匹配 → 子图遍历 → TextUnit 原文证据 → 上下文组装
14. **Global Search**：社区检测 → 社区报告 → LLM 聚合 → 宏观概括
15. **检索 Pipeline**：Intent Router → Rewriter → Retriever → RRF Fusion → Re-rank → Compress

---

## 2. 目标

| 目标 | 衡量标准 |
|------|---------|
| 知识图谱可构建 | 输入样本 .md → 输出 Neo4j 中 > 5 个实体 + > 3 个关系 |
| Local Search 可用 | 输入"用户服务用了什么技术栈" → 返回匹配实体 + 子图 + 原文证据 |
| Global Search 可用 | 输入"这个项目的整体架构" → 返回社区报告摘要 |
| 检索 Pipeline 完整 | 支持 local / global / hybrid 三种模式，结果经过重排和压缩 |
| 与块 A 联通 | 使用块 A 的 DB Session 和 LLM 客户端，不自己创建 |

---

## 3. 使用技术栈

```yaml
# === 强制使用 ===
rag_framework: llama-index>=0.11.0            # 唯一允许的 RAG 框架
  - llama-index-graph-stores-neo4j
  - llama-index-vector-stores-postgres
  - llama-index-embeddings-huggingface
  - llama-index-core

embedding:
  model: BAAI/bge-large-zh-v1.5               # 中文 Embedding（1024维）
  provider: sentence-transformers

graph_db: neo4j>=5.0                           # 图数据库 Python Driver
vector_db: pgvector                            # PostgreSQL 向量扩展（块 A 已部署）

llm_client: openai>=1.0                        # 继承块 A，兼容 DeepSeek API
test: pytest>=8.0 + pytest-asyncio             # 继承块 A
lint: ruff                                     # 继承块 A
type_check: mypy                               # 继承块 A

# === 新增容器 ===
new_services:
  - neo4j                                      # docker compose 新增

# === 禁止引入 ===
forbidden:
  - langchain, langchain-community, langchain-openai  # 全家桶禁止
  - chromadb, qdrant-client, weaviate-client          # 其他向量库
  - redis, celery                                      # 还没到引入的时候
```

---

## 4. Coding 约束

```python
# ✅ 正确：使用 LlamaIndex
from llama_index.core import PropertyGraphIndex, Document
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# ❌ 错误：使用 LangChain
# from langchain_community.graphs import Neo4jGraph        # 禁止
# from langchain.embeddings import HuggingFaceEmbeddings   # 禁止
# from langchain.text_splitter import RecursiveTextSplitter # 禁止

# ✅ 使用块 A 的 LLM 客户端，不自己 new
from app.core.llm import get_llm
llm = get_llm()  # 返回 OpenAI 客户端（兼容 DeepSeek API）

# ❌ 错误：自己创建 LLM 客户端
# from openai import OpenAI
# llm = OpenAI(api_key="...")  # 禁止
```

### 其他约束

```
- 每个函数 ≤ 50 行，每个文件 ≤ 300 行
- 所有 public 函数必须有 type hint + Google 风格 docstring
- 禁止 TODO / FIXME / pass / raise NotImplementedError
- 跨 Phase 的功能用 VIBE_DEFER(块 X) 标记
- 不做 CSV/Web/图片处理（那是块 E 的范围）
```

---

## 5. 数据结构

### 5.1 Neo4j 图谱 Schema

```yaml
节点类型 (Node Labels):
  TechStack:           # 技术栈
    properties: {name, category, version, description, embedding, confidence}
  Component:           # 系统组件
    properties: {name, type, responsibility, description}
  ArchitecturePattern: # 架构模式
    properties: {name, description, pros, cons}
  Constraint:          # 约束条件
    properties: {name, type, description, severity}
  TextUnit:            # 文本单元（Chunk 与 Entity 的桥梁）
    properties: {id, text, entities, relations, section_path, embedding}

关系类型 (Relationship Types):
  depends_on:          # A 依赖于 B
  implements:          # A 实现 B
  recommends:          # A 推荐使用 B
  conflicts_with:      # A 与 B 冲突
  alternative_to:      # A 是 B 的替代方案
  part_of:             # A 是 B 的组成部分
  extracted_from:      # Entity 提取自 TextUnit
```

### 5.2 PGVector 集合

```yaml
集合名: text_unit_embeddings
  向量维度: 1024  # BAAI/bge-large-zh-v1.5
  索引类型: IVFFlat
  存储内容: TextUnit 原文 + metadata (section_path, entity_ids)

集合名: entity_embeddings
  向量维度: 1024
  索引类型: IVFFlat
  存储内容: 实体名称 + 描述 + 类型
```

### 5.3 核心 Python 模型

```python
class KGEntity(BaseModel):
    """知识图谱实体"""
    id: str
    name: str
    type: Literal["TechStack", "Component", "ArchitecturePattern", "Constraint", "Concept"]
    category: str = ""
    description: str = ""
    properties: dict = {}
    embedding: list[float] = []
    confidence: float = 0.9

class KGRelation(BaseModel):
    """知识图谱关系"""
    id: str
    source: str          # 源实体 ID
    target: str          # 目标实体 ID
    type: str            # depends_on / implements / ...
    reason: str = ""     # 提取理由

class TextUnit(BaseModel):
    """文本单元"""
    id: str
    text: str
    entities: list[str]         # 关联实体 ID
    relations: list[str]        # 关联关系 ID
    section_path: str = ""
    embedding: list[float] = []

class ScoredDoc(BaseModel):
    """检索结果"""
    id: str
    text: str
    score: float
    source: str          # local / global / hybrid
    metadata: dict = {}
```

---

## 6. 要新增的文件

```
app/knowledge_layer/
├── __init__.py
├── config.py                              # Neo4j / PGVector / LLM 配置
├── models.py                              # KGEntity, KGRelation, TextUnit, ScoredDoc
├── pipeline.py                            # RetrievalPipeline 主入口
│
├── ingestion/
│   ├── __init__.py
│   ├── document_loader.py                 # 多格式文档加载（先只做 .md）
│   ├── chunker.py                         # 多粒度分块（Sentence/Paragraph/Section）
│   ├── entity_extractor.py                # LLM 实体提取
│   ├── relation_extractor.py              # LLM 关系提取
│   ├── entity_resolver.py                 # ⭐ 实体融合/消歧（四级策略）
│   ├── claims_extractor.py                # ⭐ Claims/Covariates 提取
│   ├── entity_embedder.py                 # ⭐ 实体多源融合 Embedding
│   ├── text_unit_builder.py               # TextUnit 构建
│   ├── knowledge_aging.py                 # ⭐ 知识老化策略（降权/归档/删除）
│   ├── kg_versioning.py                   # ⭐ 知识图谱版本控制（快照/回滚）
│   └── index_builder.py                   # LlamaIndex PropertyGraphIndex 构建
│
├── graph_store.py                         # Neo4j 封装（CRUD 实体+关系）
├── vector_store.py                        # PGVector 封装（向量读写）
│
└── retrieval/
    ├── __init__.py
    ├── intent_router.py                   # 搜索意图路由
    ├── rewriter.py                        # Query Rewriter
    ├── enricher.py                        # Query Enricher
    ├── local_search.py                    # Local Search 引擎
    ├── global_search.py                   # Global Search 引擎
    ├── fusion.py                          # RRF 融合
    ├── reranker.py                        # Cross-encoder 重排
    └── compressor.py                      # 上下文压缩

tests/unit/
├── test_ingestion.py                      # 分块/实体/关系提取单元测试
├── test_entity_resolver.py                # ⭐ 实体融合/消歧单元测试
├── test_claims_extractor.py               # ⭐ Claims 提取单元测试
├── test_knowledge_aging.py                # ⭐ 知识老化策略单元测试
├── test_kg_versioning.py                  # ⭐ 版本控制单元测试
├── test_local_search.py                   # Local Search 单元测试
└── test_global_search.py                  # Global Search 单元测试

tests/integration/
├── test_kg_build.py                       # 知识图谱构建集成测试
├── test_kg_versioning.py                  # ⭐ 版本快照/回滚集成测试
├── test_local_search.py                   # Local Search 集成测试
└── test_global_search.py                  # Global Search 集成测试
```

---

## 7. 模块联通（输入/输出接口）

### 本块对外输出

```
输出 → 块 C（Agent 流水线）:
  - RetrievalPipeline.retrieve(query, mode, top_k) → RetrievalContext
  - 块 C 通过此接口获取知识上下文

输出 → 块 D（全链路串联）:
  - 同上，Orchestrator 的 KnowledgeAugmentNode 调用本块的 Pipeline

输出 → 块 E（企业功能）:
  - 文档管理复用本块的 document_loader 和 chunker
```

### 本块对外输入

```
输入 ← 块 A:
  - app/core/llm.py: get_llm() → LLM 客户端
  - app/models/base.py: get_db_session() → DB Session
  - app/auth/deps.py: get_current_user() → 用户身份（用于租户隔离）
```

### 核心接口签名

```python
# RetrievalPipeline 对外接口
class RetrievalPipeline:
    async def retrieve(
        self,
        query: str,
        mode: str = "hybrid",        # local / global / hybrid
        top_k: int = 10,
        workspace_id: str = None,     # 租户隔离
    ) -> RetrievalContext:
        """多路检索主入口。

        Args:
            query: 用户查询文本。
            mode: 检索模式。
            top_k: 返回结果数。
            workspace_id: 工作空间 ID（租户隔离）。

        Returns:
            包含检索结果和上下文的 RetrievalContext。
        """
        ...

# KnowledgeGraphBuilder 对外接口
class KnowledgeGraphBuilder:
    async def build_from_document(
        self,
        file_path: str,
        workspace_id: str,
    ) -> BuildStats:
        """从文档构建知识图谱。

        Returns:
            BuildStats: {entities, relations, text_units, communities}
        """
        ...
```

---

## 8. 完整链路

```
文档构建链路（增强版）:
  用户上传 .md 文件
    → DocumentLoader.load(file_path)
    → MultiGranularityChunker.chunk()          # 3 级分块
    → EntityExtractor.extract(chunks)          # LLM 提取实体
    → RelationExtractor.extract(entities, chunks)  # LLM 提取关系
    → EntityResolver.resolve(entities)         # ⭐ 实体融合/消歧（四级策略）
    → ClaimsExtractor.extract(text_units)      # ⭐ Claims 声明性断言提取
    → EntityEmbedder.embed(entities, text_units, claims)  # ⭐ 多源融合 Embedding
    → TextUnitBuilder.build(chunks, entities, relations)
    → Neo4jGraphStore.upsert(entities + relations + text_units + claims)
    → PGVectorStore.upsert(text_units + claims)  # 向量化
    → LlamaIndex PropertyGraphIndex.build()     # 构建索引
    → KnowledgeGraphVersioning.create_snapshot() # ⭐ 创建版本快照
    → 返回 BuildStats

检索链路（以 Local Search 为例）:
  用户输入 "用户服务用了什么技术栈"
    → IntentRouter.route(query) → "local"
    → QueryRewriter.rewrite(query) → 3 条子查询
    → QueryEnricher.enrich(query) → 实体链接扩展
    → LocalSearch.search(query)
      → _match_entities(query) → 精确+语义匹配实体
      → _expand_subgraph(entities) → 子图遍历 1-2 跳
      → _retrieve_text_units(entities) → 原文证据
      → _assemble_context() → 结构化输出
    → RRF.fusion(图结果 + 向量结果 + BM25 结果)
    → ReRanker.rerank(query, candidates)
    → Compressor.compress(results, max_tokens=4000)
    → 返回 RetrievalContext
```

---

## 9. 测试用例

### 9.1 知识图谱构建测试

```python
# tests/integration/test_kg_build.py
async def test_build_from_markdown():
    """用样本 .md 构建知识图谱。"""
    stats = await builder.build_from_document("tests/fixtures/sample_prd.md")
    assert stats.entities >= 5
    assert stats.relations >= 3
    assert stats.text_units >= 3

async def test_neo4j_connection():
    """验证 Neo4j 可连接。"""
    driver = GraphDatabase.driver(...)
    assert driver.verify_connectivity()

async def test_pgvector_connection():
    """验证 PGVector 可连接。"""
    ...

async def test_entity_extraction():
    """验证 LLM 实体提取返回正确格式。"""
    entities = extractor.extract([chunk])
    assert all(e.name for e in entities)
    assert all(e.type in VALID_TYPES for e in entities)
```

### 9.2 实体融合测试

```python
# tests/unit/test_entity_resolver.py
async def test_exact_name_match():
    """验证精确名称匹配合并。"""
    resolver = EntityResolver()
    merged, action = await resolver.resolve(new_entity("Spring Boot"), [existing_entity("Spring Boot")])
    assert action == "merge"

async def test_alias_match():
    """验证别名匹配。"""
    merged, action = await resolver.resolve(new_entity("spring-boot"), [existing_entity("Spring Boot")])
    assert action == "merge"

async def test_semantic_match_below_threshold():
    """验证低语义相似度不合并。"""
    merged, action = await resolver.resolve(new_entity("Redis"), [existing_entity("PostgreSQL")])
    assert action == "new"
```

### 9.3 Claims 提取测试

```python
# tests/unit/test_claims_extractor.py
async def test_claims_extraction():
    """验证从 TextUnit 提取 Claims。"""
    claims = await extractor.extract([sample_text_unit], entities)
    assert len(claims) > 0
    assert all(c.subject for c in claims)
    assert all(c.claim_type in VALID_CLAIM_TYPES for c in claims)

async def test_claims_store():
    """验证 Claims 写入 Neo4j 和 PGVector。"""
    await extractor.store_claims([sample_claim])
    stored = await graph_store.get_claims_for_entity(sample_claim.subject_entity_id)
    assert len(stored) >= 1
```

### 9.4 知识老化测试

```python
# tests/unit/test_knowledge_aging.py
async def test_aging_downgrade():
    """验证 90 天未引用实体被降权。"""
    policy = KnowledgeAgingPolicy()
    stats = await policy.apply_aging()
    assert stats["downgraded"] >= 0

async def test_aging_archive():
    """验证 180 天未引用实体被归档。"""
    stats = await policy.apply_aging()
    assert stats["archived"] >= 0

async def test_aging_soft_delete():
    """验证 365 天未引用实体被软删除。"""
    stats = await policy.apply_aging()
    assert stats["deleted"] >= 0
```

### 9.5 版本控制测试

```python
# tests/unit/test_kg_versioning.py
async def test_create_snapshot():
    """验证创建版本快照。"""
    version_id = await versioning.create_snapshot("test snapshot")
    assert version_id is not None

async def test_rollback():
    """验证回滚到指定版本。"""
    v1 = await versioning.create_snapshot("v1")
    # ... 做一些修改 ...
    await versioning.rollback(v1)
    # 验证回滚后数据一致
    entities = await graph_store.get_all_entities()
    assert len(entities) == original_count
```

### 9.2 Local Search 测试

```python
# tests/integration/test_local_search.py
async def test_local_search_returns_entities():
    """验证 Local Search 返回匹配实体。"""
    result = await searcher.search("用户服务")
    assert len(result.matched_entities) > 0
    assert any("用户" in e.name for e in result.matched_entities)

async def test_local_search_returns_evidence():
    """验证 Local Search 返回原文证据。"""
    result = await searcher.search("JWT 认证")
    assert len(result.text_unit_evidence) > 0
```

### 9.3 Global Search 测试

```python
# tests/integration/test_global_search.py
async def test_global_search_returns_summary():
    """验证 Global Search 返回社区报告摘要。"""
    result = await searcher.search("整体架构")
    assert result.answer is not None
    assert len(result.answer) > 50

async def test_global_search_level_selection():
    """验证层级选择逻辑。"""
    level = searcher._select_level("整体架构", reports)
    assert level >= 1  # 宽泛查询选高层级
```

---

## 10. 验收标准

### 必须满足

```bash
# 1. 技术栈合规
pytest tests/test_tech_stack_compliance.py -v
# 输出: 3 passed

# 2. 类型检查 + 风格
mypy app/ --strict --ignore-missing-imports
ruff check app/ tests/

# 3. 全部测试通过（含块 A 回归）
pytest tests/ -v --tb=short
# 100% passed, 0 skipped, 块 A 的测试也必须绿

# 4. 无 TODO 残留
grep -rn "TODO\|FIXME\|NotImplementedError" app/ --include="*.py" || echo "CLEAN"
```

### 联通性测试

```bash
# 启动 Neo4j（块 A 的 postgres 应已在运行）
docker compose up -d neo4j

# 验证 Neo4j 联通
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
driver.verify_connectivity()
print('Neo4j 连接成功')
"

# 验证知识图谱构建
pytest tests/integration/test_kg_build.py -v
# 期望: 构建完成: 实体 >= 5, 关系 >= 3

# 验证 Local Search
pytest tests/integration/test_local_search.py -v
# 期望: 返回匹配实体+原文证据

# 验证 Global Search
pytest tests/integration/test_global_search.py -v
# 期望: 返回社区摘要

# 验证块 A 回归测试仍然全绿
pytest tests/integration/test_auth_flow.py -v
pytest tests/integration/test_db_connection.py -v
```

### 完成后状态

```
✅ .md 文档可构建为知识图谱（Neo4j + PGVector）
✅ 实体融合/消歧正常工作（同名实体自动合并）
✅ Claims 提取和存储正常（声明性断言可检索）
✅ 实体多源融合 Embedding 写入 Neo4j
✅ 知识图谱版本快照可创建和回滚
✅ 知识老化策略可执行（降权/归档/删除）
✅ Local Search 可回答具体实体问题
✅ Global Search 可回答宏观概括问题
✅ 检索结果经过重排和压缩
✅ 块 A 的 Auth、DB、LLM Gateway 仍然正常工作
✅ 可进入块 C 开发
```
