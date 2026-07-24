# 块 B：知识层（数据 + 检索）

> 关联总文档：`prd2tsd.md` §三 Knowledge Layer — 完整设计
>
> **前置条件**：块 A 已完成且全部测试通过。本块使用块 A 提供的 DB Session、Auth 中间件、LLM Gateway、Contract 接口、数据脱敏引擎。

---

## 1. 需求描述

构建**实体增强的双路检索**系统：文档上传 → 分块 + 实体提取 → 多路检索 + 反思纠偏。这是系统的数据底座，所有后续 Agent Layer 的分析和规划都依赖本块的检索能力。

### 核心功能列表

1. **文档加载**：支持 .md 文件的多格式加载和解析
2. **多粒度分块**：Sentence / Paragraph / Section 三级分块策略
3. **实体提取**：LLM 驱动的技术实体提取（TechStack / Component / ArchitecturePattern 等）
4. **实体融合/消歧**（Entity Resolution）：精确匹配 → 别名匹配两级策略
5. **实体 Embedding**：名称 + 描述 双源融合
6. **Neo4j 存储**：图数据库写入实体节点
7. **PGVector 存储**：向量化 Chunk 和 Entity Embedding
8. **Local Search**：实体匹配 → 子图遍历 → 原文证据 → 上下文组装
9. **Global Search**：实体类型分组 → 社区报告 → LLM 聚合 → 宏观概括
10. **检索 Pipeline**：Intent Router → Rewriter → Retriever → RRF Fusion → Re-rank → Compress
11. **⭐⭐ 检索反思**（Reflection）：每次检索后 LLM 判断结果质量，不满足时自动修正查询并重新检索

---

## 2. 目标

| 目标 | 衡量标准 |
|------|---------|
| 知识图谱可构建 | 输入样本 .md → 输出 Neo4j 中 > 5 个实体 |
| Local Search 可用 | 输入"用户服务用了什么技术栈" → 返回匹配实体 + 子图 + 原文证据 |
| Global Search 可用 | 输入"这个项目的整体架构" → 返回社区报告摘要 |
| 检索 Pipeline 完整 | 支持 local / global / hybrid 三种模式，结果经过重排和压缩 |
| 与块 A 联通 | 使用块 A 的 DB Session 和 LLM 客户端，不自己创建 |

---

## 3. 使用技术栈

```yaml
# === 强制使用 ===
rag_framework: 无                        # 核心链路自实现，不依赖 RAG 框架
  # 注：requirements.txt 中保留 llama-index-* 作为可选补充层（index_builder.py）
  #     但核心构建和检索链路不依赖 LlamaIndex

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
# ✅ 使用块 A 的 LLM 客户端，不自己 new
from app.core.llm import get_llm
llm = get_llm()  # 返回 OpenAI 客户端（兼容 DeepSeek API）

# ❌ 错误：自己创建 LLM 客户端
# from openai import OpenAI
# llm = OpenAI(api_key="...")  # 禁止

# ❌ 错误：使用 LangChain 全家桶
# from langchain_community.graphs import Neo4jGraph        # 禁止
# from langchain.embeddings import HuggingFaceEmbeddings   # 禁止
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
  KGEntity:            # 知识图谱实体（统一标签，type 属性区分 TechStack/Component 等）
    properties: {id, name, type, category, description, embedding, confidence, workspace_id}

关系类型：不预先定义，实体间关联由查询时 LLM 现场推理得出
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
│   ├── entity_resolver.py                 # 实体融合/消歧（两级策略）
│   └── entity_embedder.py                 # 实体 Embedding（名称+描述双源）
│
├── graph_store.py                         # Neo4j 封装（实体 CRUD）
├── vector_store.py                        # PGVector 封装（向量读写）
│
└── retrieval/
    ├── __init__.py
    ├── intent_router.py                   # 搜索意图路由
    ├── rewriter.py                        # Query Rewriter
    ├── enricher.py                        # Query Enricher
    ├── local_search.py                    # Local Search 引擎
    ├── global_search.py                   # Global Search 引擎
    ├── reflection.py                      # ⭐ 检索反思裁判（新增）
    ├── fusion.py                          # RRF 融合
    ├── reranker.py                        # Cross-encoder 重排
    └── compressor.py                      # 上下文压缩

tests/unit/
├── test_ingestion.py                      # 分块/实体提取单元测试
├── test_entity_resolver.py                # 实体融合/消歧单元测试
├── test_local_search.py                   # Local Search 单元测试
├── test_global_search.py                  # Global Search 单元测试
└── test_reflection.py                     # ⭐ 检索反思单元测试

tests/integration/
├── test_kg_build.py                       # 知识图谱构建集成测试
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
文档构建链路:
  用户上传 .md 文件
    → DocumentLoader.load(file_path)
    → MultiGranularityChunker.chunk()          # 3 级分块
    → EntityExtractor.extract(chunks)          # LLM 提取实体
    → EntityResolver.resolve_batch(entities)   # 两级消歧（精确+别名）
    → EntityEmbedder.embed_entity(entity)      # 双源融合（名称+描述）
    → Neo4jGraphStore.upsert_entities(resolved) # Neo4j 写入实体
    → PGVectorStore.upsert_text_unit(chunks)   # PGVector 写入分块向量
    → PGVectorStore.upsert_entity_embedding()  # PGVector 写入实体向量
    → 返回 BuildStats

检索链路（含反思循环）:
  用户输入 "用户服务用了什么技术栈"
    → IntentRouter.route(query) → "local"
    → QueryRewriter.rewrite(query) → 3 条子查询
    → QueryEnricher.enrich(query) → 实体链接扩展
    → LocalSearch.search(query)
      → _match_entities(query) → 关键词匹配实体
      → _expand_subgraph(entities) → 子图遍历 1-2 跳
      → _retrieve_chunks(entities) → 原文证据
      → _assemble_context() → 结构化输出
    → RRF.fusion(图结果 + 向量结果)
    → ⭐ ReflectionJudge.judge()
      ├── "accept" → 继续
      └── "refine" → 修正查询 → 重新检索（最多 2 轮）
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
    assert stats.chunks >= 3

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
```

### 9.3 检索反思测试

```python
# tests/unit/test_reflection.py
async def test_reflection_accept():
    """验证结果匹配时返回 accept。"""
    result = await judge.judge("支付系统", quality_results)
    assert result.judgment == "accept"

async def test_reflection_refine():
    """验证结果不匹配时生成修正查询。"""
    result = await judge.judge("支付系统", empty_results)
    assert result.judgment == "refine"
    assert result.refined_query != ""
```

### 9.4 Local Search 测试

```python
# tests/integration/test_local_search.py
async def test_local_search_returns_entities():
    """验证 Local Search 返回匹配实体。"""
    result = await searcher.search("用户服务")
    assert len(result.matched_entities) > 0
```

### 9.5 Global Search 测试

```python
# tests/integration/test_global_search.py
async def test_global_search_returns_summary():
    """验证 Global Search 返回架构摘要。"""
    result = await searcher.search("整体架构")
    assert result.answer is not None
    assert len(result.answer) > 50
```

---

## 10. 验收标准

### 必须满足

```bash
# 1. 类型检查 + 风格
mypy app/ --strict --ignore-missing-imports
ruff check app/ tests/

# 2. 全部测试通过（含块 A 回归）
pytest tests/ -v --tb=short
# 100% passed, 0 skipped, 块 A 的测试也必须绿

# 3. 无 TODO 残留
grep -rn "TODO\|FIXME\|NotImplementedError" app/ --include="*.py" || echo "CLEAN"
```

### 联通性测试

```bash
# 启动 Neo4j（块 A 的 postgres 应已在运行）
docker compose up -d neo4j

# 验证知识图谱构建
pytest tests/integration/test_kg_build.py -v
# 期望: 构建完成: 实体 >= 5

# 验证 Local Search + 反思
pytest tests/integration/test_local_search.py -v
pytest tests/unit/test_reflection.py -v
# 期望: 返回匹配实体，反思循环可触发

# 验证 Global Search
pytest tests/integration/test_global_search.py -v
# 期望: 返回架构摘要

# 验证块 A 回归测试仍然全绿
pytest tests/integration/test_auth_flow.py -v
pytest tests/integration/test_db_connection.py -v
```

### 完成后状态

```
✅ .md 文档可构建实体索引（Neo4j + PGVector）
✅ 实体融合/消歧正常工作（同名+别名自动合并）
✅ 实体 Embedding（名称+描述双源）写入 PGVector
✅ Local Search 可回答具体实体问题
✅ Global Search 可回答宏观概括问题
✅ 检索反思裁判可自动纠偏不匹配的查询
✅ 检索结果经过反思→重排→压缩
✅ 块 A 的 Auth、DB、LLM Gateway 仍然正常工作
✅ 可进入块 C 开发
```
