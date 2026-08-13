# PRD2TSD Agents — 全链路架构与运行时深度解析

> **版本**: v2.0  
> **日期**: 2026-07-28  
> **目标读者**: Agent 开发面试准备、系统架构理解、新成员 onboarding  
> **行数**: 5000+

---


---



---

## 目录

- [一、系统概述](#一系统概述)
- [二、基础设施层（Block A）](#二基础设施层block-a)
- [三、知识层（Block B）](#三知识层block-b)
- [四、Agent 流水线层（Block C）](#四agent-流水线层block-c)
- [五、主编排层（Block D）](#五主编排层block-d)
- [六、企业级功能层（Block E）](#六企业级功能层block-e)
- [七、生产级加固层（Block F）](#七生产级加固层block-f)
- [八、高级模式增强（Block G）](#八高级模式增强block-g)
- [九、主线任务全链路逐节点详解](#九主线任务全链路逐节点详解)
- [十、chat / knowledge_qa 路径全链路](#十chat--knowledge_qa-路径全链路)
- [十一、断点恢复与 Human-in-the-Loop 全链路](#十一断点恢复与-human-in-the-loop-全链路)
- [十二、历史消息处理全链路](#十二历史消息处理全链路)
- [十三、SSE 流式推送全链路](#十三sse-流式推送全链路)
- [十四、LLM 调用全链路（Gateway + LangChain 适配器）](#十四llm-调用全链路gateway--langchain-适配器)
- [十五、LangGraph 与 LangChain 的分工设计](#十五langgraph-与-langchain-的分工设计)
- [十六、关键技术决策与架构原则](#十六关键技术决策与架构原则)
- [十七、面试要点：核心卖点总结](#十七面试要点核心卖点总结)

---


---

---

## 一、系统概述

### 1.1 一句话定义

**PRD2TSD Agents** 是一个基于 **LangGraph + LangChain** 的 **Multi-Agent 系统**，输入产品需求文档（PRD），经过 **知识检索 → 需求分析 → 架构规划 → 方案生成 → 质量评测** 五步流水线，自动输出完整的技术方案文档。附带企业级的 **多租户权限、SSE 流式推送、护栏安全、熔断降级、记忆增强** 等生产级能力。

### 1.2 核心价值

| 价值维度 | 描述 |
|---------|------|
| **自动化** | 将数天的人工方案编写缩短到分钟级 |
| **标准化** | 14 章节标准化输出，确保方案文档质量一致 |
| **可迭代** | Evaluation 低分自动回退重做，最多 3 轮迭代 |
| **可审核** | Human-in-the-Loop 机制，关键节点人工确认 |
| **可恢复** | PostgreSQL Checkpointer 持久化，崩溃后可断点续传 |
| **可观测** | OpenTelemetry 全链路追踪 + Prometheus 指标 + SSE 实时推送 |
| **企业级** | RBAC/ABAC 权限、多租户隔离、数据脱敏、预算控制、审计日志 |

### 1.3 技术栈全景

```
┌──────────────────────────────────────────────────────────────────┐
│                       技术栈全景                                  │
├──────────────────────────────────────────────────────────────────┤
│  Agent 框架:      LangGraph 0.2+（StateGraph）                   │
│  Agent 节点内部:   LangChain Core（ChatPromptTemplate + Pydantic  │
│                   OutputParser + GatewayChatModel）              │
│  LLM 接入:        自研 LLM Gateway（OpenAI SDK 兼容多 Provider）  │
│  Web 框架:        FastAPI 0.110+ (async)                         │
│  ORM:             SQLAlchemy 2.0 (async) + Alembic               │
│  数据库:           PostgreSQL 16 + PGVector（向量检索）           │
│  图数据库:         Neo4j 5.x（知识图谱）                          │
│  缓存/队列:        Redis 7.x（Celery 任务队列）                   │
│  对象存储:         MinIO（文档/图片存储）                         │
│  Embedding:       BAAI/bge-large-zh-v1.5 (1024d)                │
│  文档入图:         multi_format_loader（pdf/csv/docx/md/图片）    │
│  追踪:            OpenTelemetry → Jaeger                        │
│  指标:            Prometheus → Grafana                           │
│  LLM 观测:        LangFuse                                        │
│  LLM 模型:        DeepSeek-V3（主）/ GPT-4o-mini（降级/Judge）    │
│  测试:            Pytest + pytest-asyncio                        │
│  Lint:            Ruff + Mypy                                    │
└──────────────────────────────────────────────────────────────────┘
```

### 1.4 系统分层架构

```
┌──────────────────────────────────────────────────────────────┐
│  用户交互层:  FastAPI REST  │  Streamlit UI  │  CLI          │
├──────────────────────────────────────────────────────────────┤
│  主编排层:    LangGraph Orchestrator（StateGraph）            │
│              意图分类 → 记忆检索 → 知识检索 → 4层Agent →     │
│              记忆压缩 → 会话保存 → 迭代决策                   │
│              + Human-in-the-Loop / SSE 流式推送              │
├──────────────────────────────────────────────────────────────┤
│  Agent 层:    4 个独立 StateGraph                             │
│              Analysis → Planning → Generation → Evaluation   │
├──────────────────────────────────────────────────────────────┤
│  知识层:      实体增强双路检索 + ReflectionJudge              │
│              文档摄取 → 多粒度分块 → 实体提取 →               │
│              Neo4j 图存储 + PGVector 向量存储                 │
├──────────────────────────────────────────────────────────────┤
│  企业增强:    SSE流式 │ 会话历史 │ 文档管理 │ 统一交互入口  │
│              URL文档 │ 多格式入图 │ 批量任务 │ Webhook通知  │
├──────────────────────────────────────────────────────────────┤
│  生产加固:    工具系统 │ 护栏拦截 │ 熔断器 │ Failover链      │
│              记忆增强 │ Prompt管理 │ 行为回放 │ 结构化输出   │
├──────────────────────────────────────────────────────────────┤
│  基础设施:    PostgreSQL+PGVector │ Neo4j │ Redis │ MinIO    │
│              LLM Gateway │ OpenTelemetry │ Prometheus        │
└──────────────────────────────────────────────────────────────┘
```

---


---

---

## 二、基础设施层（Block A）

### 2.1 概述

基础设施层是整个系统的底座，所有后续模块都依赖本层提供的数据库连接、认证授权、多租户隔离、LLM 调用能力。

### 2.2 模块清单

| 模块 | 目录 | 核心文件 |
|------|------|---------|
| 数据库模型 | `app/models/` | SQLAlchemy ORM 模型（users/workspaces/roles/sessions 等） |
| 认证授权 | `app/auth/` | JWT 签发/验证、RBAC 权限检查、FastAPI 中间件 |
| 多租户 | `app/auth/` | 工作空间 CRUD、团队成员管理、租户上下文传递 |
| 连接管理 | `app/core/connections/` | PostgreSQL/Redis/MinIO/Neo4j 生命周期管理 |
| 配置中心 | `app/core/config.py` | pydantic-settings 三级优先级配置 |
| LLM Gateway | `app/llm_gateway/` | Provider 抽象、模型路由、成本追踪、语义缓存 |
| 数据安全 | `app/security/` | 数据分级（L1-L4）、脱敏引擎、审计日志 |
| Contracts | `contracts/` | 跨 Layer 接口和数据模型定义 |
| 数据库迁移 | `alembic/` | 版本化数据库 Schema 管理 |

### 2.3 数据库模型详解

#### 2.3.1 核心表结构

```sql
-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    auth_provider VARCHAR(32) NOT NULL,   -- 'jwt' / 'keycloak' / 'wecom'
    auth_id VARCHAR(255) NOT NULL,
    status VARCHAR(16) DEFAULT 'active',
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
    UNIQUE(auth_provider, auth_id)
);

-- 组织表
CREATE TABLE organizations (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(64) UNIQUE NOT NULL,
    plan VARCHAR(32) DEFAULT 'free',     -- free / pro / enterprise
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ
);

-- 工作空间表（多租户隔离单元）
CREATE TABLE workspaces (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(64) NOT NULL,
    knowledge_scope VARCHAR(32) DEFAULT 'workspace',
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ,
    UNIQUE(organization_id, slug)
);

-- 角色表
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organizations(id),
    name VARCHAR(64) NOT NULL,
    is_system BOOLEAN DEFAULT FALSE,
    permissions JSONB NOT NULL,          -- ["workspace:read", "prd:write", ...]
    created_at TIMESTAMPTZ
);

-- 团队成员表
CREATE TABLE team_members (
    id UUID PRIMARY KEY,
    workspace_id UUID REFERENCES workspaces(id),
    user_id UUID REFERENCES users(id),
    role_id UUID REFERENCES roles(id),
    joined_at TIMESTAMPTZ,
    UNIQUE(workspace_id, user_id)
);

-- 会话表
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    workspace_id UUID REFERENCES workspaces(id),
    user_id UUID REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    session_type VARCHAR(32) DEFAULT 'generate',
    status VARCHAR(16) DEFAULT 'active',
    thread_id UUID,                      -- LangGraph checkpoint 绑定
    summary TEXT,
    message_count INT DEFAULT 0,
    token_count INT DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    rating SMALLINT,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ
);

-- 会话消息表
CREATE TABLE session_messages (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    role VARCHAR(16) NOT NULL,           -- user / assistant / system / tool
    content TEXT NOT NULL,
    content_type VARCHAR(32) DEFAULT 'text',
    attachments JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',         -- 模型/token/延迟等
    parent_message_id UUID,
    created_at TIMESTAMPTZ
);

-- LLM 调用日志表
CREATE TABLE llm_call_logs (
    id UUID PRIMARY KEY,
    task_id UUID,
    workspace_id UUID REFERENCES workspaces(id),
    model VARCHAR(64) NOT NULL,
    layer VARCHAR(32),                   -- analysis/planning/generation/evaluation
    node VARCHAR(64),
    input_tokens INT NOT NULL,
    output_tokens INT NOT NULL,
    cost DECIMAL(10,6) NOT NULL,
    latency_ms INT,
    cached BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ
);
```

### 2.4 认证授权架构

#### 2.4.1 JWT 双 Token 机制

```
access_token (15分钟) + refresh_token (7天)
     │
     ├─ 登录: POST /api/v1/auth/login → 返回双 token
     ├─ 访问: Authorization: Bearer {access_token}
     ├─ 刷新: POST /api/v1/auth/refresh → 用 refresh_token 换新 access_token
     └─ 登出: POST /api/v1/auth/logout → 加入黑名单
```

#### 2.4.2 RBAC + ABAC 混合权限

```
权限模型:
  RBAC（基于角色）:
    超级管理员 → 组织管理员 → 项目管理员 → 架构师 → 开发者 → 查看者

  ABAC（基于属性）:
    资源级权限字符串:
    - workspace:{id}:read        查看工作空间
    - workspace:{id}:write       编辑工作空间
    - prd:{id}:read              查看PRD
    - prd:{id}:write             编辑PRD
    - scheme:{id}:review         审核方案
    - knowledge:{id}:admin       管理知识库条目
    - team:{id}:manage           管理团队成员

  FastAPI 中间件:
    请求 → AuthMiddleware
      ├─ 解析 JWT → 验证签名 + 过期时间
      ├─ 获取用户角色 + 权限列表
      ├─ 注入 TenantContext → 贯穿整个请求生命周期
      └─ 校验资源权限 → 通过/拒绝
```

### 2.5 LLM Gateway 核心架构

#### 2.5.1 设计目标

将多模型调用统一为一个门面，提供以下能力：

| 能力 | 描述 |
|------|------|
| Provider 抽象 | 统一接口（OpenAI/Anthropic/Cohere/本地） |
| 模型路由 | 按 task_type 自动选择模型 |
| 成本追踪 | 每次调用记录 token + 费用到 llm_call_logs |
| 语义缓存 | 相同查询命中缓存，不重复调用 |
| 速率限制 | 按 workspace 维度的 RPM/TPM 限制 |
| 预算控制 | workspace 月预算超 90% 自动降级 |

#### 2.5.2 配置三级优先级

```
环境变量（最高优先级）
    ↓ 覆盖
.env 文件
    ↓ 覆盖
代码默认值（最低优先级）

示例:
  MODEL_CONFIG__LLM__DEEPSEEK__API_KEY=sk-xxx  ← 环境变量
  覆盖:
  MODEL_CONFIG.LLM.DEEPSEEK.API_KEY=sk-yyy     ← .env
  覆盖:
  api_key=""                                     ← 代码默认
```

#### 2.5.3 支持的模型类型

```python
# 5 种模型类型，统一通过 ModelConfigManager 管理
model_types = {
    "llm":        [DeepSeek-V3, GPT-4o-mini, ...],
    "embedding":  [text-embedding-3-small, BAAI/bge-large-zh-v1.5, ...],
    "rerank":     [cohere-rerank-v3, ...],
    "judge":      [GPT-4o-mini, ...],        # 评测用低成本模型
}
```

### 2.6 数据安全架构

#### 2.6.1 数据分类分级

```
L1 (公开):    项目名称、技术栈名称
L2 (内部):    架构设计、代码片段
L3 (机密):    API Key、数据库密码、用户邮箱
L4 (绝密):    加密密钥、支付信息

数据脱敏流程:
  原始文本 → DataClassifier.classify() → 识别 L3/L4 数据
          → DataMaskingEngine.mask() → 正则匹配 + SHA-256 替换
          → 脱敏后文本 → 发送给 LLM
```

#### 2.6.2 审计日志

```
哈希链不可篡改审计:
  AuditLogEntry(n) → SHA-256(AuditLogEntry(n-1).hash + Entry(n).data)
  每个审计条目包含前一条的哈希，形成不可篡改链
```

---


---

---

## 三、知识层（Block B）

### 3.1 概述

知识层是系统的数据底座，构建**实体增强的双路检索**系统：文档上传 → 分块 + 实体提取 → 多路检索 + 反思纠偏。所有后续 Agent Layer 的分析和规划都依赖本块的检索能力。

### 3.2 核心设计：双路检索架构

```
                    用户查询
                        │
                        ▼
              ┌─────────────────┐
              │  IntentRouter   │ ← 判断 local / global / hybrid
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    Local Search  Global Search  Hybrid
          │            │            │
    ┌─────┴─────┐      │      ┌─────┴─────┐
    │ Neo4j 图  │      │      │ Neo4j +   │
    │ + PGVector│      │      │ PGVector  │
    └─────┬─────┘      │      └─────┬─────┘
          │            │            │
          └────────────┼────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │   RRFFusion     │ ← 倒数排名融合
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ ReflectionJudge │ ← LLM 判断检索质量
              │  accept/refine  │    不满足 → 修正查询 → 重新检索
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │    ReRanker     │ ← Cross-encoder 精排
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │   Compressor    │ ← 上下文去冗余
              └────────┬────────┘
                       │
                       ▼
                 RetrievalContext
```

### 3.3 知识图谱构建流程

```
文档上传 (.md / .pdf / .docx / .csv / .txt)
    │
    ▼
DocumentLoader.load(file_path)
    │  ├─ .md  → 直接读取
    │  ├─ .pdf → docling 解析
    │  └─ .docx → python-docx 解析
    │
    ▼
MultiGranularityChunker.chunk(text, level="paragraph")
    │  三级分块策略:
    │  ├─ Sentence  (句子级): 30词/块
    │  ├─ Paragraph (段落级): 200词/块
    │  └─ Section   (章节级): 1000词/块
    │
    ▼
EntityExtractor.extract(chunks)
    │  LLM 驱动的技术实体提取:
    │  实体类型: TechStack / Component / ArchitecturePattern /
    │           Constraint / Concept / Datastore / API / Service
    │
    ▼
EntityResolver.resolve(new_entities, existing_entities)
    │  两级策略:
    │  ├─ 精确匹配: 实体名称完全相同 → 合并
    │  └─ 别名匹配: 实体名称相似度 > 0.85 → 合并
    │
    ▼
EntityEmbedder.embed(entities)
    │  双源融合:
    │  ├─ 名称 Embedding (权重 0.6)
    │  └─ 描述 Embedding (权重 0.4)
    │  模型: BAAI/bge-large-zh-v1.5 (1024d)
    │
    ▼
Neo4j 写入 + PGVector 写入
    │
    ▼
BuildStats { entities_created, entities_merged, chunks_indexed, duration_ms }
```

### 3.4 Local Search（本地搜索）详解

```
用户查询: "用户服务用了什么技术栈？"
    │
    ▼
1. QueryRewriter.rewrite(query)
    │  改写查询（扩展同义词、拆分复合查询）
    │  "用户服务" → "user-service" / "用户微服务"
    │
    ▼
2. QueryEnricher.enrich(query)
    │  用实体链接丰富查询
    │  识别 "用户服务" 是已知实体 → 加入实体 ID
    │
    ▼
3. LocalSearch 双路检索:
    │
    ├─ 路径 A: PGVector 向量检索
    │    ├─ 查询 Embedding (1024d)
    │    ├─ IVFFlat 近似最近邻搜索
    │    ├─ top_k = 10
    │    └─ 返回 ScoredDoc 列表（chunk 原文 + 分数）
    │
    └─ 路径 B: Neo4j 图检索
         ├─ 实体匹配: MATCH (e:KGEntity) WHERE e.name CONTAINS '用户服务'
         ├─ 子图遍历: MATCH (e)-[r*1..2]-(related) RETURN e, r, related
         ├─ 原文证据: 从关联的 chunk 节点获取原文
         └─ 返回 ScoredDoc 列表（实体 + 关系 + 证据）
    │
    ▼
4. RRFFusion.fuse(local_results_a, local_results_b)
    │  倒数排名融合:
    │  score = 1 / (k + rank_a) + 1 / (k + rank_b)
    │  k = 60（平滑参数）
    │
    ▼
5. ReflectionJudge.judge(query, fused_results)
    │  LLM 判断检索质量:
    │  ├─ 满足 → accept → 继续
    │  └─ 不满足 → refine → 返回修正查询 → 重新检索（最多 3 轮）
    │     refined_query: "用户微服务的技术栈选型"
    │
    ▼
6. ReRanker.rerank(query, results)
    │  Cross-encoder 精排（LLM 语义重排）
    │
    ▼
7. Compressor.compress(results)
    │  去冗余、截断过长文本
    │
    ▼
返回 RetrievalContext
```

### 3.5 Global Search（全局搜索）详解

```
用户查询: "这个项目的整体架构"
    │
    ▼
1. 实体类型分组
    │  将所有 KGEntity 按 type 分组:
    │  ├─ TechStack: [PostgreSQL, Redis, Neo4j, ...]
    │  ├─ Component: [UserService, OrderService, ...]
    │  ├─ ArchitecturePattern: [微服务, 事件驱动, ...]
    │  └─ ...
    │
    ▼
2. LLM 聚合
    │  将按类型聚合的实体作为输入
    │  "TechStack: [PostgreSQL, Redis, Neo4j...]\nComponent: [UserService, OrderService...]"
    │  生成宏观架构概述
    │
    ▼
返回 RetrievalContext（宏观层面的架构概述）
```

### 3.6 检索反思（ReflectionJudge）

这是知识层最核心的**自我纠偏机制**：

```python
class ReflectionJudge:
    """检索结果反思裁判。

    工作流程:
    1. LLM 判断检索结果是否满足用户需求
    2. 不满足时:
       a. 分析缺少什么信息
       b. 生成修正后的搜索查询
       c. 重新检索（最多 3 轮）
    3. 满足时: 接受结果，继续后续流程
    """

    async def judge(self, query: str, results: list[ScoredDoc]) -> ReflectionResult:
        # 格式化检索结果
        formatted = self._format_results(results)

        # LLM 判断
        prompt = REFLECTION_PROMPT.format(query=query, results=formatted)
        response = await gateway.complete(prompt, temperature=0.1)

        # 解析 JSON 响应
        result = self._parse_response(response.content)

        if result.judgment == "refine":
            logger.info("检索反思: 需要修正查询 → %s", result.refined_query)
            # 调用方会用 refined_query 重新检索

        return result
```

### 3.7 文件结构

```
app/knowledge_layer/
├── __init__.py
├── config.py              # Neo4j / PGVector / LLM 配置
├── models.py              # KGEntity, ScoredDoc, Chunk, Claim, RetrievalContext
├── pipeline.py            # RetrievalPipeline + KnowledgeGraphBuilder 主入口
│
├── ingestion/             # 文档摄取
│   ├── document_loader.py     # 多格式文档加载（.md/.pdf/.docx/.csv）
│   ├── chunker.py             # 多粒度分块（Sentence/Paragraph/Section）
│   ├── entity_extractor.py    # LLM 实体提取
│   ├── entity_resolver.py     # 实体融合/消歧（两级策略）
│   ├── entity_embedder.py     # 实体 Embedding（名称+描述双源）
│   └── claims_extractor.py   # Claims 决策断言提取
│
├── graph_store.py         # Neo4j 封装（实体 CRUD + 子图遍历）
├── vector_store.py        # PGVector 封装（向量读写 + IVFFlat 索引）
│
└── retrieval/             # 检索引擎
    ├── intent_router.py       # 搜索意图路由（local/global/hybrid）
    ├── rewriter.py            # Query Rewriter
    ├── enricher.py            # Query Enricher
    ├── local_search.py        # Local Search 引擎（Neo4j + PGVector）
    ├── global_search.py       # Global Search 引擎（实体聚合 + LLM 宏观总结）
    ├── reflection.py          # ReflectionJudge（检索反思裁判）
    ├── fusion.py              # RRF 倒数排名融合
    ├── reranker.py            # Cross-encoder 精排
    └── compressor.py          # 上下文压缩
```

### 3.8 与 Block C 的联通方式

```
Block C Planning Layer → KnowledgeAugmentNode
    │
    └─→ RetrievalPipeline.retrieve(
            query=prd_raw[:500],
            mode="hybrid",
            top_k=10,
            workspace_id=workspace_id,
        )
        → RetrievalContext
        → 注入 PlanningState["knowledge_context"]
```

---


---

---

## 四、Agent 流水线层（Block C）

### 4.1 概述

4 个独立的 Agent Layer，每个 Layer 是一个 LangGraph StateGraph，可独立运行和测试，100% 通过 `contracts/interfaces.py` 解耦。

### 4.2 解耦设计原则

```
┌────────────────────────────────────────────────────────────┐
│  4 个 Layer 之间 100% 通过 contracts/interfaces.py 解耦     │
│                                                             │
│  C1 (Analysis) 输出 → AnalysisResultDetail                  │
│  C2 (Planning)  输入 AnalysisResultDetail                   │
│                  输出 → PlanningResultDetail                │
│  C3 (Generation) 输入 PlanningResultDetail                  │
│                  输出 → GenerationResultDetail              │
│  C4 (Evaluation) 输入全部三个 Result                        │
│                  输出 → EvaluationReportDetail              │
│                                                             │
│  ❌ 禁止：C2 的 Node 直接 import C1 的 Node                  │
│  ❌ 禁止：任何 Layer 直接引用 OrchestratorState               │
│  ✅ 允许：通过 contracts/models.py 共享数据模型               │
└────────────────────────────────────────────────────────────┘
```

### 4.3 C1 — Analysis Layer（分析层）

#### 4.3.1 节点拓扑

```
DocumentParserNode
    │  解析 PRD 为结构化章节
    ▼
LanguageDetectorNode
    │  中/英/混合自动检测（英文自动翻译为中文）
    ▼
RequirementExtractorNode
    │  功能需求（FR-xxx）+ 非功能需求（NFR-xxx）提取
    ▼
ConstraintAnalyzerNode
    │  约束条件提取（技术/性能/时间/预算/合规/团队）
    ▼
DependencyAnalyzerNode
    │  需求依赖关系图分析（A 依赖 B，C 阻塞 D...）
    ▼
DomainClassifierNode
    │  领域标签（电商/金融/医疗/SaaS/IoT...）
    ▼
RequirementQualityNode
    │  6 维评分: 完整性/清晰度/可测试性/一致性/必要性/可行性
    │  每维 0-10 分
    ▼
EffortEstimatorNode
    │  COCOMO II + LLM 工作量估算（人月）
    ▼
StakeholderAnalyzerNode
    │  干系人分析（产品经理/架构师/开发者/运维...→关注点）
    ▼
ClarityCheckerNode
    │  需求清晰度检查（模糊描述标记）
    ▼
AnalysisResultAssemblerNode
    │  汇总为 AnalysisResultDetail
```

#### 4.3.2 关键数据流

```python
class AnalysisState(TypedDict):
    prd_raw: str                          # 输入的 PRD 原文
    prd_sections: list[DocumentSection]    # 解析后的结构化章节
    language: str                         # 检测到的语言（zh/en/mixed）
    extracted_requirements: list[RequirementDetail]  # 提取的需求
    extracted_constraints: list[ConstraintDetail]    # 提取的约束
    dependency_graph: DependencyGraph               # 依赖关系图
    domain_tags: list[str]                          # 领域标签
    quality_scores: dict[str, float]                # 质量评分
    effort_estimate: EffortEstimate                 # 工作量估算
    stakeholders: list[Stakeholder]                 # 干系人列表
    clarity_issues: list[ClarityIssue]              # 清晰度问题
    analysis_result: AnalysisResultDetail           # 最终汇总
```

#### 4.3.3 节点内部的 LangChain 使用

每个节点内部使用统一模式：

```python
class RequirementExtractorNode:
    def __init__(self, llm: GatewayChatModel):
        self.llm = llm  # LangChain BaseChatModel 适配器

    async def run(self, state: AnalysisState) -> AnalysisState:
        # 1. LangChain ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{prd_text}"),
        ])

        # 2. PydanticOutputParser 做结构化输出
        parser = PydanticOutputParser(pydantic_object=RequirementList)

        # 3. LCEL 链: prompt | llm | parser
        chain = prompt | self.llm | parser

        # 4. 异步调用
        result = await chain.ainvoke({"prd_text": state["prd_raw"]})

        # 5. 写入 State
        state["extracted_requirements"] = result.requirements
        return state
```

### 4.4 C2 — Planning Layer（规划层）

#### 4.4.1 节点拓扑

```
KnowledgeAugmentNode
    │  调用 Block B 的 RetrievalPipeline → 获取相关知识上下文
    ▼
PatternRecommendNode
    │  2-3 架构模式候选 + 对比分析（微服务 vs 单体 vs 事件驱动...）
    ▼
TechStackSelectionNode
    │  分维度技术选型（后端/前端/数据库/缓存/消息队列/部署...）
    ▼
ComponentDecompositionNode
    │  需求 → 组件映射（UserService / OrderService / Gateway...）
    ▼
DataArchitectureNode
    │  数据架构设计（ER 图 / 数据流 / 存储策略）
    ▼
ApiPlanningNode
    │  API 规划草稿（RESTful / GraphQL / gRPC 端点设计）
    ▼
DeploymentPlanningNode
    │  部署方案草稿（K8s / Docker Compose / 云服务选型）
    ▼
CostEstimationNode
    │  3 种成本方案: 低成本 / 标准 / 高可用
    ▼
TimelinePlanningNode
    │  甘特图 + 里程碑（Phase 1/2/3 时间线）
    ▼
SkillGapAnalysisNode
    │  当前团队技能 vs 方案需求 → 缺口分析
    ▼
RiskQuantificationNode
    │  风险概率 × 影响矩阵
    ▼
PlanSelfCheckNode
    │  自检 → 通过或回退
    ▼
PlanAssemblerNode
    │  汇总为 PlanningResultDetail
```

#### 4.4.2 输出模型

```python
class PlanningResultDetail(BaseModel):
    architecture_patterns: list[PatternEval]  # 架构模式候选+对比
    tech_stack: list[TechChoiceDetail]        # 技术选型
    components: list[ComponentDetail]         # 系统组件分解
    data_architecture: DataArchitectureDetail # 数据架构
    api_plan: ApiPlanDetail                   # API 规划
    deployment_plan: DeploymentPlanDetail     # 部署方案
    cost_estimates: list[CostEstimate]        # 成本估算（3 方案）
    timeline: TimelineDetail                  # 时间线
    skill_gaps: list[SkillGap]               # 技能缺口
    risks: list[RiskItem]                     # 风险量化
    metadata: dict                            # 元数据（含 node_outputs）
```

### 4.5 C3 — Generation Layer（生成层）

#### 4.5.1 节点拓扑

```
OutlineGeneratorNode
    │  14 标准章节大纲生成
    ▼
TemplateSelectorNode
    │  三级模板系统: 行业模板 / 企业模板 / 章节模板
    │  使用 Jinja2 渲染
    ▼
SectionWriterNode（可并行扇出）
    │  逐节撰写 → 每节调用 LLM 流式生成
    │  ↓ GatewayChatModel.stream_complete() 逐 token
    │  ↓ EventBus.publish("generation.chunk")
    ▼
MermaidDiagramNode
    │  Mermaid 架构图自动生成（C4/时序图/ER图）
    ▼
CodeScaffoldNode
    │  真实可编译代码框架（非描述文本）
    │  支持 Java/Go/Python/TypeScript
    ▼
ConsistencyCheckerNode
    │  一致性检查 → 修复矛盾
    │  检查: 术语一致性 / 数据流一致性 / 接口一致性
    ▼
RevisionNode
    │  根据一致性检查结果修改文档
    ▼
MultiFormatExporterNode
    │  多格式导出: Markdown / PDF / DOCX / HTML
    │  使用 WeasyPrint (PDF) / python-docx (DOCX)
    ▼
DocumentAssemblerNode
    │  最终 Markdown 组装
```

#### 4.5.2 14 标准章节

```
1.  项目概述
2.  需求分析
3.  架构总览
4.  技术栈选型
5.  组件设计
6.  数据架构
7.  API 设计
8.  安全设计
9.  部署方案
10. 性能设计
11. 监控与运维
12. 测试策略
13. 成本估算
14. 风险与缓解
```

#### 4.5.3 流式生成原理

```python
class SectionWriterNode:
    async def run(self, state: GenerationState) -> GenerationState:
        # 流式调用 LLM
        full_text = ""
        async for token in self.llm.stream_complete(
            prompt=section_prompt,
            task_type="generation.section_writer",
            max_tokens=4096,
        ):
            full_text += token

            # 每 200 字符推送一次 SSE
            if len(full_text) % 200 < len(token) + 1:
                await event_bus.publish(
                    f"task:{state['task_id']}",
                    SseEvent(
                        type="generation.chunk",
                        payload={"content": token, "section": section_name},
                    ),
                )

        state["section_contents"][section_name] = full_text
        return state
```

### 4.6 C4 — Evaluation Layer（评测层）

#### 4.6.1 10 维评分体系

| 维度 | 权重 | 评估内容 |
|------|------|---------|
| prd_coverage | 15% | PRD 需求覆盖率 |
| consistency | 15% | 方案内部一致性 |
| feasibility | 15% | 技术可行性 |
| architecture_quality | 15% | 架构质量 |
| security | 10% | 安全合规 |
| cost | 5% | 成本合理性 |
| implementability | 10% | 可实施性 |
| tech_advancement | 5% | 技术先进性 |
| legal_compliance | 5% | 法律合规 |
| completeness | 5% | 文档完整度 |

#### 4.6.2 评分校准机制

```python
class ScoreCalibrator:
    """评分校准器 — 三种校准策略。

    1. 历史比对校准:
       将当前评分与历史同类型项目的评分分布对比
       如果偏离超过 2σ → 标记为异常

    2. 平行评测校准:
       同一方案用两个不同 Judge 模型评测
       如果分数差异 > 15% → 触发人工复核

    3. 反馈闭环:
       人工审核后的修正分数 → 更新校准参数
    """
```

#### 4.6.3 节点拓扑

```
CoverageCheckerNode        ← PRD 需求覆盖率
ConsistencyCheckerNode     ← 内部一致性
FeasibilityEvaluatorNode   ← 技术可行性
ArchitectureQualityNode    ← 架构质量评分
SecurityComplianceNode     ← 安全合规
CostEvaluatorNode          ← 成本评估
ImplementabilityNode       ← 可实现性
TechAdvancementNode        ← 技术先进性
LegalComplianceNode        ← 法律合规
ScoringNode                ← 10 维加权综合评分
ScoreCalibrator            ← 评分校准
```

---


---

---

## 五、主编排层（Block D）

### 5.1 概述

主编排层通过 LangGraph StateGraph 把 Block C 的 4 个独立 Agent Layer 串联起来，加上 Adapter 适配层、Human-in-the-Loop 机制、迭代决策，实现端到端流水线。

### 5.2 核心设计：三层数据模型

```python
# 1. Config 层 — 启动时加载，只读
class OrchestratorConfig(BaseModel):
    max_iterations: int = 3
    evaluation_pass_threshold: float = 85.0
    evaluation_replan_threshold: float = 70.0
    max_llm_retries: int = 3
    keepalive_interval: int = 30
    session_ttl_days: dict = {"free": 30, "pro": 180}

# 2. State 层 — LangGraph checkpoint 自动持久化
class OrchestratorState(TypedDict):
    task_id: str
    prd_raw: str
    prd_file_type: str
    workspace_id: str
    user_id: str
    # ... 所有 4 层的结果字段 ...
    status: Literal["running", "paused", "complete", "failed"]
    progress: float
    iteration_count: int

# 3. Runtime 层 — 每次请求注入，不参与 checkpoint 序列化
class OrchestratorRuntime:
    db_session: Any          # 数据库会话
    event_bus: Any           # SSE 事件总线
    llm_gateway: Any         # LLM Gateway
    current_user_id: str
    current_workspace_id: str
    started_at: datetime
```

### 5.3 Adapter 模式（状态映射）

每个 Agent Layer 外层包装一个 Adapter，做 `OrchestratorState ↔ LayerState` 的双向映射。这保证了 Layer 的独立性——Layer 只需要知道自己的 State 结构，不需要知道 Orchestrator 的存在。

```python
# AnalysisAdapter 示例
class AnalysisAdapter:
    def __init__(self, analysis_graph: StateGraph):
        self.graph = analysis_graph  # 已编译的 Analysis StateGraph

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        # 1. 提取 Analysis Layer 需要的输入
        analysis_input = {
            "prd_raw": state["prd_raw"],
            "knowledge_context": state.get("knowledge_context"),
        }

        # 2. 调用 Block C 的独立 StateGraph
        result = await self.graph.ainvoke(analysis_input)

        # 3. 映射回 OrchestratorState
        state["analysis_result"] = result["analysis_result"]
        state["extracted_requirements"] = result["extracted_requirements"]
        state["extracted_constraints"] = result["extracted_constraints"]
        state["progress"] = 0.30
        return state
```

### 5.4 主编排图节点拓扑

```
classify              ← 意图分类（chat/knowledge_qa/complex_generation/clarification）
    │
    ├─→ chat_node          ← 纯对话 LLM 回答
    ├─→ retrieve_node      ← 知识库查询（检索 + LLM 回答）
    ├─→ clarify_node       ← 提示补充信息
    │
    └─→ retrieve_memory    ← 历史记忆检索（MemoryRetriever）
         │
         ▼
    knowledge_retrieval    ← 知识库检索（RetrievalPipeline）
         │
         ▼
    analysis               ← AnalysisAdapter（C1）
         │
         ▼
    needs_review?          ← 条件路由
         ├─ skip → planning
         └─ review → analysis_human_review
                         │
                         ▼ (interrupt 暂停)
                    (人工审核后 resume)
                         │
                         ▼
    planning               ← PlanningAdapter（C2）
         │
         ▼
    needs_review?          ← 条件路由
         ├─ skip → generation
         └─ review → planning_human_review
                         │
                         ▼ (interrupt 暂停)
                    (人工审核后 resume)
                         │
                         ▼
    generation             ← GenerationAdapter（C3）
         │
         ▼
    evaluation             ← EvaluationAdapter（C4）
         │
         ▼
    IterationDecider       ← 条件路由
         ├─ score≥85 → final_assembly
         ├─ score≥70 → replan / regenerate
         └─ score<70 → replan / human_intervention
              │
              ▼ (循环最多 3 轮)
    final_assembly         ← 最终组装 + Webhook 通知
         │
         ▼
    compress_memory         ← 记忆压缩（ContextCompressor）
         │
         ▼
    save_session            ← 会话持久化（sessions + session_messages 表）
         │
         ▼
    END
```

### 5.5 迭代决策逻辑

```python
class IterationDecider:
    def run(self, state: OrchestratorState) -> str:
        report = state["evaluation_report"]
        iteration = state["iteration_count"]
        max_iter = state["max_iterations"]

        # 达到最大迭代次数 → 强制接受
        if iteration >= max_iter:
            return "final_assembly"

        # 评分 >= 85 → 通过
        if report.overall_score >= 85:
            return "final_assembly"

        # 评分 >= 70 → 根据子维度决定
        if report.overall_score >= 70:
            if report.dimension_scores["consistency"] < 70:
                return "generation"     # 重新生成
            if report.dimension_scores["feasibility"] < 70:
                return "planning"       # 重新规划
            return "final_assembly"

        # 评分 < 70 + 有严重问题 → 人工介入
        if report.critical_issues:
            return "analysis_human_review"

        # 评分 < 70 → 重新规划
        return "planning"
```

---


---

---

## 六、企业级功能层（Block E）

### 6.1 SSE 流式推送（EventBus）

#### 6.1.1 架构设计

```
Publisher                          Subscriber
─────────                          ─────────
TaskManager._execute_task()        GET /api/v1/tasks/{task_id}/events
  ├─ task.created                    │
  ├─ task.progress                   │
  ├─ task.review_required            │
  └─ done                            │
       │                             │
ChatNode / KnowledgeQANode           │
  ├─ chat.chunk                      │
  └─ qna.chunk                       │
       │                             │
SectionWriterNode                    │
  └─ generation.chunk                │
       │                             │
       ▼                             ▼
┌──────────────────────────────────────────┐
│        EventBus（asyncio.Queue Pub/Sub）  │
│                                          │
│  _channels = {                           │
│    "task:abc123": {queue1, queue2},      │
│    "task:def456": {queue3},              │
│  }                                       │
│                                          │
│  publish(channel, event):                │
│    for queue in _channels[channel]:      │
│      queue.put_nowait(event)  ← 非阻塞   │
│                                          │
│  subscribe(channel) → asyncio.Queue      │
│  unsubscribe(channel, queue)             │
└──────────────────────────────────────────┘
       │
       ▼
SSE 端点 → SSEResponse
  async for event in queue:
    yield f"data: {event.to_sse_line()}\\n\\n"
  + 30s keepalive 心跳
```

#### 6.1.2 14 种 SSE 事件类型

| 事件类型 | 触发时机 | Payload 关键字段 |
|---------|---------|-----------------|
| `task.created` | 任务创建成功 | task_id, status |
| `task.progress` | 每节点执行完毕 | progress (0.0~1.0), stage |
| `task.log` | 日志消息 | level, message |
| `task.status` | 状态变更 | status (running/paused/complete/failed) |
| `task.review_required` | 需要人工审核 | task_id, stage |
| `task.review_resolved` | 审核已处理 | task_id, stage, decision |
| `task.saved` | 会话已保存 | task_id, status, score |
| `generation.chunk` | 流式文档片段 | content, section |
| `generation.section` | 章节状态变更 | section_name, status |
| `chat.chunk` | 对话流式片段 | content |
| `qna.chunk` | Q&A 流式片段 | content |
| `qna.status` | Q&A 阶段变更 | phase (retrieving/generating) |
| `keepalive` | 30s 心跳 | 空 |
| `done` | 任务完成 | task_id, result_summary |
| `error` | 错误事件 | message, code |

### 6.2 会话历史管理

#### 6.2.1 完整功能矩阵

| 功能 | 实现方式 |
|------|---------|
| 创建会话 | `SessionRepository.create_session()` + 自动生成 thread_id |
| 会话列表 | 分页 + 筛选（status/type）+ 排序（last_message_at） |
| 消息查看 | 按 session_id 查询 session_messages 表，按 created_at 排序 |
| 会话搜索 | PostgreSQL FTS 全文搜索（`to_tsvector('simple', content)`） |
| 会话导出 | Markdown / JSON 格式导出 |
| 会话续接 | 通过 thread_id 恢复 LangGraph checkpoint |
| 老化清理 | Free 30天 / Pro 180天 / Enterprise 不限 |
| LLM 摘要 | 任务完成后 SessionSummarizer 自动生成标题和摘要 |

#### 6.2.2 会话与 LangGraph 的绑定

```
Session.thread_id = LangGraph checkpoint thread_id

创建会话时:
  session = Session(thread_id=str(uuid4()), ...)
  → sessions 表

执行任务时:
  config = {"configurable": {"thread_id": session.thread_id}}
  orchestrator.astream(initial_state, config)
  → LangGraph 自动通过 PostgresSaver 在 PG 中保存该 thread 的 checkpoint

续接会话时:
  session = get_session(session_id)
  config = {"configurable": {"thread_id": session.thread_id}}
  orchestrator.astream(new_state, config)
  → LangGraph 自动加载历史 checkpoint，retrieve_memory 获取之前对话
```

### 6.3 文档管理

```
上传流程:
  用户上传文件 (.md/.pdf/.docx/.txt/.csv/.tsv/.png)
    │
    ├─ 校验: 文件类型 + 文件大小（最大 50MB）
    ├─ SHA-256 哈希 → DocumentDeduplicator 去重检查
    ├─ 存储到 MinIO（对象存储）
    ├─ 写入 PostgreSQL 文档元数据
    └─ 多格式自动入图（pdf/csv/docx/md/txt/png/jpg）:
          multi_format_loader 提取文本 → KnowledgeGraphBuilder.build_from_bytes
          → 实体提取 → Neo4j + PGVector（Celery 异步，processing_status 跟踪）
```

### 6.4 Web 资源索引

```
URL 抓取流程:
  WebLoader.fetch(url)
    ├─ Readability 正文提取 → Markdown
    ├─ 知识图谱增量更新
    └─ PGVector 向量索引

递归爬虫:
  WebCrawler.crawl(seed_url, max_depth=3)
    ├─ BFS 遍历同域链接
    ├─ robots.txt 尊重
    ├─ 并发控制（最多 5 并发）
    └─ 每个页面 → WebLoader 处理

定时同步:
  WebSyncScheduler
    ├─ ETag / Last-Modified 变更检测
    ├─ 内容哈希变更检测
    └─ 仅变更页面触发重新索引
```

### 6.5 统一交互入口（POST /api/v1/interact）

```
交互分发:
  IntentClassifier 意图识别（URL/doc_id 强信号 + 规则 + LLM 两级）
    ├─ chat / knowledge_qa / clarification → 主编排图（classify 节点幂等跳过）
    ├─ complex_generation → 异步任务（同步返回 task_id / 流式 SSE task.*）
    └─ document_analysis → 文档分析（URL 抓取/已上传文档）
流式模式: stream=true → text/event-stream（复用 E12 EventBus）
```

### 6.6 URL 文档分析（SSRF 防护 + 入库）

```
URL 文档流程:
  url_security.validate_url (协议白名单 + 内网拦截 + DNS 二次检查)
    → WebLoader.fetch → Markdown
    → UrlDocumentService.ingest → uploaded_documents(file_type=url + source_url)
    → 入库检索（可按文件名/标题搜索）
    → generate=true 一键生成 TSD（转 complex_generation）
```

### 6.7 批量处理与定时任务（Celery Beat）

```python
BEAT_SCHEDULE = {
    "refresh-knowledge-graph": {
        "task": "prd2tsd.batch.tasks.refresh_knowledge_graph",
        "schedule": 86400,  # 每 24 小时
    },
    "cleanup-expired-sessions": {
        "task": "prd2tsd.batch.tasks.cleanup_expired_sessions",
        "schedule": 3600,   # 每小时
    },
    "sync-web-resources": {
        "task": "prd2tsd.batch.tasks.sync_web_resources",
        "schedule": 7200,   # 每 2 小时
    },
}
# 文档入图任务（上传后异步触发）:
#   index_document_to_kg(document_id)
```

### 6.8 多格式自动入图

```
上传即入图（pdf/csv/docx/md/txt/png/jpg）:
  service.upload()
    → multi_format_loader.extract_text(bytes, filename)
    → KnowledgeGraphBuilder.build_from_bytes(content, filename, workspace_id)
    → build_from_text 链路（分块→实体提取→消歧→Neo4j→PGVector）
状态跟踪: pending → processing → indexed / failed（processing_error）
```

---


---

---

## 七、生产级加固层（Block F）

### 7.1 工具系统（Tool Registry）

#### 7.1.1 设计目标

让 LLM 能自主选择工具（Function Calling），替代原来各 Layer 各自定义 `tools.py` 的情况。

#### 7.1.2 核心接口

```python
class BaseTool(ABC):
    name: str                            # 工具名（LLM 通过此名选择）
    description: str                     # 描述（LLM 理解用途）
    parameters: type[BaseModel]          # Pydantic 参数模型 → 自动 JSON Schema
    required_permissions: list[str] = [] # 调用所需权限
    timeout: float = 30.0                # 执行超时

    @abstractmethod
    async def execute(self, ctx: ToolContext, **params) -> ToolResult:
        ...

class ToolRegistry:
    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool): ...

    @classmethod
    def get_schemas(cls, agent_name, permissions) -> list[dict]:
        """返回 OpenAI Function Calling Schema 列表"""
        # 按 agent_name 筛选 + 按 permissions 筛选
        # 返回 [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]

    @classmethod
    async def execute(cls, name, ctx, **params) -> ToolResult:
        """执行工具（含超时/鉴权/追踪）"""
```

### 7.2 护栏系统（Guardrails）

#### 7.2.1 7 个可插拔护栏

```
pre_llm 阶段（调用 LLM 前）:
  ├─ PromptInjectionGuardrail      ← 检测提示注入攻击
  ├─ PIIDetectorGuardrail          ← 检测并脱敏 PII 数据
  └─ TimeoutGuardrail              ← 检查 CircuitBreaker 状态

post_llm 阶段（LLM 返回后）:
  ├─ ContentSafetyGuardrail        ← 检测不安全内容
  ├─ OutputValidatorGuardrail      ← 校验输出格式（JSON Schema 验证）
  ├─ EmptyResponseGuardrail        ← 检测空响应
  └─ RetryDecisionGuardrail        ← 决定是否重试/降级

护栏结果驱动 LangGraph 路由:
  GuardrailResult { passed, blocked, reason, severity, metadata: {retry, fallback_model, max_retries} }
    → LangGraph 条件边 route_after_guardrail()
    → retry / blocked / continue
```

### 7.3 熔断器（Circuit Breaker）

#### 7.3.1 状态机

```
                    ┌─────────┐
         连续失败 N 次│         │ 超时恢复
       ┌───────────→│  OPEN   │←───────────┐
       │            │ (熔断)  │            │
       │            └────┬────┘            │
       │                 │                 │
       │           等待超时                 │
       │                 │                 │
       │            ┌────▼────┐      试探失败
       │            │HALF_OPEN│────────────┘
       │            │(半开)   │
       │            └────┬────┘
       │                 │
       │           试探成功
       │                 │
┌──────┴──────┐          │
│   CLOSED    │←─────────┘
│  (正常工作)  │
└─────────────┘
```

#### 7.3.2 使用方式

```python
# 装饰器式使用
circuit_breaker = CircuitBreaker(
    name="provider:deepseek",
    failure_threshold=3,       # 连续 3 次失败 → OPEN
    recovery_timeout=30.0,     # 30 秒后 → HALF_OPEN
    half_open_max_requests=1,  # 半开时最多 1 个试探请求
)

# 在 Gateway 中使用
result = await circuit_breaker.call(
    provider.complete,
    prompt="...",
    model="deepseek-chat",
)
```

### 7.4 Provider Failover 链

```python
class FailoverManager:
    """自动切换 Provider 的 Failover 管理器。

    Failover 链配置:
      LLM: deepseek-chat (P0) → gpt-4o-mini (P1)
      Embedding: text-embedding-3-small

    工作流程:
      1. 调用 Primary Provider
      2. 失败 → 标记 Primary 为 unhealthy
      3. 自动切换到下一个 Fallback Provider
      4. 定期健康检测（每 60 秒 ping）
      5. Primary 恢复 → 自动切回
    """

    async def call_with_failover(self, model_type, **kwargs):
        for attempt in range(max_attempts):
            target = await self.get_target(model_type)  # 获取当前健康 Target
            try:
                result = await self._call_provider(target, **kwargs)
                return result
            except Exception:
                await self.record_failure(model_type, target.provider)  # 切下一个
        raise AllProvidersUnavailableError(model_type)
```

### 7.5 记忆增强（MemoryRetriever + ContextCompressor）

#### 7.5.1 记忆检索策略

```python
class MemoryRetriever:
    """多策略融合检索:

    recency:    最近 N 条消息加权（指数衰减，24h 半衰期）
    relevance:  语义向量相似度 / 关键词重叠
    importance: LLM 判断重要性（0-1 分）
    hybrid:     三策略加权融合（recency:0.3 + relevance:0.4 + importance:0.3）
    """
```

#### 7.5.2 上下文压缩策略

```python
class ContextCompressor:
    """Token 超限时自动压缩:

    summarize: 对最旧的消息做 LLM 摘要（保留语义）
    rolling:   丢弃最旧的消息（保留最新 N 轮）
    truncate:  直接截断最早的消息文本

    策略优先级: summarize → rolling → truncate
    """
```

### 7.6 Prompt 版本管理

```python
class PromptRegistry:
    """Prompt 版本管理:

    - 版本化存储（PromptVersion: v1.0 → v1.1 → v2.0）
    - 回滚到任意历史版本
    - Diff 对比（显示 Prompt 变更内容）
    - A/B 测试（按百分比分流到不同 Prompt 版本）
    """
```

### 7.7 Agent 行为回放

```python
class DecisionRecorder:
    """记录 Agent 每一步的完整决策过程:

    记录内容:
    - LLM 输入（完整 Prompt）
    - LLM 输出（原始响应 + Tool Calls）
    - State 变化（执行前后的 diff）
    - 性能数据（耗时、Token 消耗）
    - 可用工具列表

    回放功能:
    - 按 task_id 重演整个决策链
    - 对比不同参数/模型的结果差异
    - 用于调试和优化 Agent 行为
    """
```

### 7.8 结构化输出（LangChain PydanticOutputParser）

```python
# 替代原来的 call_llm() + json.loads() + 手动解析
# 使用 GatewayChatModel + PydanticOutputParser

from langchain_core.output_parsers import PydanticOutputParser
from app.llm_gateway.langchain_adapter import GatewayChatModel

# 定义输出模型
class RequirementList(BaseModel):
    requirements: list[RequirementItem]

# LangChain 链式调用
parser = PydanticOutputParser(pydantic_object=RequirementList)
llm = GatewayChatModel(task_type="analysis", layer="analysis")
chain = prompt | llm | parser

# 一次调用完成: Prompt 构建 → LLM 调用 → JSON 解析 → Pydantic 验证
result: RequirementList = await chain.ainvoke({"prd_text": prd_raw})
```

### 7.9 多租户 Prompt 隔离

```python
# app/auth/prompts/manager.py

class PromptManager:
    """多租户 Prompt 隔离:

    三级回退机制:
    1. 组织自定义 Prompt → 最高优先级
    2. 行业模板 Prompt → 中优先级
    3. 系统默认 Prompt → 兜底

    示例:
    org_id="acme-corp", agent="analysis", node="requirement"
      → 先查 acme-corp 的自定义 Prompt
      → 不存在 → 查 acme-corp 所在行业的模板
      → 仍不存在 → 使用系统默认 Prompt

    支持 Jinja2 模板变量:
    "请为 {{company_name}} 的 {{industry}} 业务分析需求..."
    """
```

---


---

---

## 八、高级模式增强（Block G）

### 8.1 概述

Block G 将当前基础的线性 StateGraph 升级为原生 LangGraph 高级模式。

### 8.2 Send() 并行扇出

```
当前（串行）:                    目标（并行）:
  coverage                        FanOutEval
    ↓ 2s                        ┌──┼──┬──┬──┬──┬──┬──┬──┐
  consistency                    ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼
    ↓ 2s                        C  C  F  A  S  C  I  T  L
  feasibility                   o  o  e  r  e  o  m  e  e
    ↓ 2s                        v  n  a  c  c  s  p  c  g
  ... (9 个节点)                e  s  s  h       t  h  a
    ↓                           r  i  i  _           l
  scoring                       a  s  b  q           _
    ↓                           g  t  i  u
  总耗时: ~18s (9 × 2s)         e  e  l  a
                                e  n  i  l
                                   c  t  i
                                   y  y  t
                                      y
                                  总耗时: ~2s (max(单节点延迟))
```

```python
# 实现方式: Send() API
from langgraph.constants import Send

def fan_out_eval(state):
    """生成 9 个 Send 并行任务。"""
    return [
        Send("coverage", state),
        Send("consistency", state),
        Send("feasibility", state),
        # ... 共 9 个
    ]

graph.add_conditional_edges("fan_out_eval", fan_out_eval, EVALUATOR_NODES)
# 9 个节点并行执行 → 自动 Fan-In 到 scoring 节点
```

### 8.3 原生 Subgraph

```
当前（手工 Adapter）:              目标（原生 Subgraph）:
  AnalysisAdapter                    graph.add_node("analysis",
    ↓                                  analysis_graph.compile())
    self.graph.ainvoke(input)        → LangGraph 自动管理子图生命周期
    ↓                                → 子图内部的 checkpoint 与主图合并
    映射回 state                     → interrupt 可穿透子图
```

### 8.4 Command() 节点内路由

```python
# 替代条件边中的复杂逻辑
from langgraph.types import Command

class SmartNode:
    async def run(self, state):
        result = await self.analyze(state)

        if result.needs_review:
            # 直接在节点内决定下一跳
            return Command(goto="human_review", update={"status": "paused"})
        elif result.is_complete:
            return Command(goto=END, update={"status": "complete"})
        else:
            return Command(goto="next_step", update=state)
```

### 8.5 生产级持久化（PostgresSaver）

```python
from langgraph.checkpoint.postgres import PostgresSaver

# 替代 MemorySaver（内存实现，重启丢失）
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
checkpointer.setup()  # 自动创建 langgraph_checkpoints 表

graph = builder.compile(checkpointer=checkpointer)

# 特性:
# - 每次节点执行后自动持久化到 PostgreSQL
# - 服务重启后可以恢复
# - 支持 Time-Travel 调试（get_state / update_state）
# - 支持多线程并发
```

---


---

---

## 九、主线任务全链路逐节点详解

> 以下是一次 "complex_generation" 任务的完整执行链路，包含每个节点的输入/输出/副作用。

### Step 0: 系统初始化

```
FastAPI lifespan 事件:
  1. connection_manager.startup()
     ├─ PostgreSQLConnector.connect() → SQLAlchemy async engine
     ├─ RedisConnector.connect() → redis-py async client
     ├─ Neo4jConnector.connect() → neo4j async driver
     └─ MinIOConnector.connect() → minio client

  2. PostgresSaver.from_conn_string(DATABASE_URL)
     └─ 创建 langgraph_checkpoints 表

  3. 构建 4 个 Agent Layer StateGraph
     ├─ build_analysis_graph().compile()
     ├─ build_planning_graph().compile()
     ├─ build_generation_graph().compile()
     └─ build_evaluation_graph().compile()

  4. build_orchestrator_graph(...)
     └─ 注入 4 个 Layer + RetrievalPipeline + SessionService
        + ContextCompressor + MemoryRetriever + LLMGateway

  5. 编译主编排图
     └─ orchestrator = graph.compile(checkpointer=PostgresSaver)

  6. 初始化全局单例
     ├─ EventBus()
     ├─ TaskManager(event_bus)
     └─ LLMGateway(...)
```

### Step 1: 用户请求 → 意图分类

```
POST /api/v1/interact
  Body: { "message": "帮我设计一个电商平台的技术方案，要求支持高并发..." }

  app/api/routes/interact.py :: interact()
    │
    ├─ Step 1.1: IntentClassifier.classify(user_input)
    │     │
    │     ├─ 规则匹配（快路径）:
    │     │     "设计" + "技术方案" + "高并发"
    │     │     → 命中 GENERATION_PATTERNS
    │     │     → intent = COMPLEX_GENERATION, confidence = 0.95
    │     │
    │     └─ 返回 IntentResult(intent=COMPLEX_GENERATION, confidence=0.95)
    │
    ├─ Step 1.2: intent == COMPLEX_GENERATION → 创建异步任务
    │     task_id = task_manager.create_task(
    │         prd_raw="帮我设计一个电商平台的技术方案...",
    │         workspace_id="ws-001",
    │         user_id="user-001",
    │     )
    │     └─ 返回 task_id = "abc-123-def"
    │
    └─ 返回 HTTP 200:
        {
          "intent": "complex_generation",
          "confidence": 0.95,
          "message": "已创建生成任务: abc-123-def",
          "session_id": ""
        }
```

### Step 2: TaskManager 创建异步任务

```
TaskManager.create_task()
  │
  ├─ task_id = "abc-123-def"
  ├─ thread_id = "xxx-yyy-zzz"  ← uuid4，用于 LangGraph checkpoint
  ├─ task_record = {
  │     "task_id": "abc-123-def",
  │     "status": "running",
  │     "progress": 0.0,
  │     "stage": "",
  │     "thread_id": "xxx-yyy-zzz",
  │     "orchestrator": compiled_orchestrator_graph,  ← 持有编译后的图
  │     ...
  │   }
  ├─ self._tasks["abc-123-def"] = task_record
  ├─ EventBus.publish("task:abc-123-def", SseEvent("task.created"))
  └─ asyncio.create_task(self._execute_task(...))  ← 不阻塞 HTTP 响应
```

### Step 3: _execute_task 核心执行

```python
async def _execute_task(self, task_id, prd_raw, ...):
    # 1. 构造初始状态
    initial_state = make_initial_state(
        task_id=task_id,
        prd_raw=prd_raw,
        prd_file_type="md",
        workspace_id=workspace_id,
        user_id=user_id,
        user_role="developer",
        permissions=["workspace:read", "workspace:write"],
    )

    # 2. LangGraph 配置（绑定 thread_id 用于 checkpoint）
    config = {"configurable": {"thread_id": thread_id}}

    # 3. 逐节点执行（astream 模式 — 每节点执行完 yield）
    async for step_state in orchestrator.astream(initial_state, config):
        # 每个节点执行完 → LangGraph 自动写入 PostgresSaver checkpoint

        # 读取中间进度
        progress = step_state.get("progress", 0.0)
        stage = step_state.get("stage", "")

        # 推送 SSE 进度事件
        await self._emit("task.progress", {
            "task_id": task_id,
            "progress": progress,
            "stage": stage,
        })

    # 4. astream 结束后的处理
    if final_state["status"] == "complete":
        await self._update_result(task_id, final_state)
        # → 写入内存 result + 推送 done 事件
    else:
        # 图被 interrupt 暂停 → 标记 paused
        # → 推送 task.review_required 事件
```

### Step 4: 主编排图逐节点执行

#### 节点 4.1: `classify` — 意图分类

```
Node: classify (IntentClassifyNode)
  输入: state["prd_raw"]
  内部:
    IntentClassifier.classify(user_input)
      → 规则匹配 → intent = "complex_generation"
  输出:
    state["intent"] = "complex_generation"
    state["intent_confidence"] = 0.95
    state["intent_sub"] = "tech_solution"

条件路由: route_by_intent(state)
  intent = "complex_generation" → 路由到 "kg_retrieve" (即 retrieve_memory 节点)
  PostgresSaver: 写入 checkpoint_1
```

#### 节点 4.2: `retrieve_memory` — 历史记忆检索

```
Node: retrieve_memory (RetrieveMemoryNode)
  输入: state["prd_raw"], state["_history_messages"]
  内部:
    MemoryRetriever.retrieve(
      query=prd_raw[:500],
      messages=history_messages,
      strategy="hybrid",
      top_k=10,
    )
    → 如果没有历史消息 → 跳过
  输出:
    state["retrieved_memories"] = []  (新任务，无历史)
  PostgresSaver: 写入 checkpoint_2
```

#### 节点 4.3: `knowledge_retrieval` — 知识库检索

```
Node: knowledge_retrieval (KnowledgeRetrievalNode)
  输入: state["prd_raw"], state["workspace_id"]
  内部:
    DecisionRecorder.start_trace(task_id)  ← Block F 行为回放

    RetrievalPipeline.retrieve(
      query=prd_raw[:500],
      mode="hybrid",
      top_k=10,
      workspace_id="ws-001",
    )

    内部流程:
      IntentRouter → "hybrid" 模式
      QueryRewriter → "电商平台 技术方案 高并发 架构设计"
      QueryEnricher → 识别实体: "电商" → 已知领域
      LocalSearch:
        ├─ PGVector: "电商平台" → 向量检索 → [ScoredDoc(微服务架构...), ...]
        └─ Neo4j: MATCH (e:KGEntity) WHERE e.name CONTAINS '电商'
                  → [KGEntity(电商平台), KGEntity(高并发), ...]
      GlobalSearch: 实体类型分组 → LLM 宏观总结
      RRFFusion: k=60, 融合 Local + Global 结果
      ReflectionJudge:
        query="电商平台 技术方案 高并发"
        results=[ScoredDoc(...), ...]
        → LLM 判断: "结果包含电商架构和高并发方案" → accept
      ReRanker: Cross-encoder 精排 → 重排序
      Compressor: 去冗余 → 压缩到 2000 tokens

  输出:
    state["knowledge_context"] = RetrievalContext {
      query: "电商平台 技术方案 高并发 架构设计",
      results: [ScoredDoc(...), ...],  ← 10 条精排结果
      mode: "hybrid",
    }
    state["progress"] = 0.10
  PostgresSaver: 写入 checkpoint_3
```

#### 节点 4.4: `analysis` — 需求分析

```
Node: analysis (AnalysisAdapter)
  输入: state["prd_raw"], state["knowledge_context"], state["tenant_context"]
  内部:
    1. 提取分析层输入:
       analysis_input = {
         "prd_raw": state["prd_raw"],
         "knowledge_context": state["knowledge_context"],
         "system_prompt": PromptManager.get("acme-corp", "analysis", "requirement"),
       }

    2. 调用 Analysis Layer StateGraph.ainvoke(analysis_input):
       parse → lang_detect → requirement → constraint → dependency
       → domain → quality → effort → stakeholder → clarity → assemble

       每个节点内部模式:
         ChatPromptTemplate | GatewayChatModel | PydanticOutputParser

       关键输出:
         - extracted_requirements: [
             RequirementDetail(id="FR-001", title="用户注册登录", ...),
             RequirementDetail(id="FR-002", title="商品管理", ...),
             RequirementDetail(id="NFR-001", title="支持10000 QPS", ...),
             ...
           ]
         - domain_tags: ["电商", "B2C", "高并发"]
         - quality_scores: {completeness: 8, clarity: 7, ...}
         - effort_estimate: {person_months: 24, confidence: 0.8}
         - stakeholders: [产品经理, 架构师, 前端开发, 后端开发, DBA, ...]

    3. 映射回 OrchestratorState:
       state["analysis_result"] = AnalysisResultDetail(...)
       state["extracted_requirements"] = [...]
       state["extracted_constraints"] = [...]
       state["progress"] = 0.30

  PostgresSaver: 写入 checkpoint_4
```

#### 节点 4.5: `needs_review` — 条件路由

```
条件路由函数: needs_review(state)
  检查:
    tenant_context.settings["auto_approve"] == True? → 否
    user_role == "admin"? → 否

  返回: "review_needed" → 路由到 analysis_human_review
```

#### 节点 4.6: `analysis_human_review` — 人工审核

```
Node: analysis_human_review (HumanReviewNode("analysis"))
  输入: state["analysis_result"], state["extracted_requirements"], state["extracted_constraints"]

  内部:
    1. 构造审核上下文:
       review_context = {
         "stage": "analysis",
         "task_id": "abc-123-def",
         "description": "分析结果审核",
         "data": {
           "analysis_result": state["analysis_result"],
           "requirements_count": 15,
           "constraints_count": 5,
         },
       }

    2. feedback = interrupt(review_context)  ← ⚠️ 图执行暂停！

  PostgresSaver: 写入 checkpoint_5（暂停点）

  TaskManager 检测:
    astream 结束，final_state["status"] 仍为 "running"
    → 标记 task 为 "paused"
    → EventBus.publish("task:abc-123-def", SseEvent("task.review_required"))
    → EventBus.publish("task:abc-123-def", SseEvent("task.status", {status: "paused"}))

  ───────── 等待人工操作 ─────────

  用户在前端看到审核界面:
    - 15 条需求
    - 5 条约束
    - 领域标签: 电商/B2C/高并发
    - 按钮: [通过] [需要修改]

  用户点击 "通过":
    POST /api/v1/review/abc-123-def/analysis
    Body: { "decision": "approved", "comment": "需求分析准确" }

  TaskManager.resolve_review("abc-123-def", "analysis", "approved", "需求分析准确")
    → task_record["status"] = "resuming"
    → asyncio.create_task(_resume_task(...))

  _resume_task:
    config = {"configurable": {"thread_id": "xxx-yyy-zzz"}}
    resume_value = {"decision": "approved", "comment": "需求分析准确"}

    async for step_state in orchestrator.astream(Command(resume=resume_value), config):
      # LangGraph 从 PostgresSaver 加载 checkpoint_5
      # 在 analysis_human_review 节点中:
      #   interrupt() 返回 resume_value
      #   decision = "approved" → state["status"] = "running"
      #   继续执行 → 返回 state

    → 图继续执行下一个节点: planning
```

#### 节点 4.7: `planning` — 架构规划

```
Node: planning (PlanningAdapter)
  输入: state["analysis_result"], state["knowledge_context"]
  内部:
    1. 提取规划层输入:
       planning_input = {
         "analysis_result": state["analysis_result"],
         "knowledge_context": state["knowledge_context"],
       }

    2. 调用 Planning Layer StateGraph.ainvoke(planning_input):
       knowledge_augment → pattern_recommend → tech_stack_selection
       → component_decomposition → data_architecture → api_planning
       → deployment_planning → cost_estimation → timeline_planning
       → skill_gap → risk_quantification → self_check → assemble

       关键输出:
         - architecture_patterns: [
             PatternEval(name="微服务", score=8.5, pros=[...], cons=[...]),
             PatternEval(name="事件驱动", score=7.0, pros=[...], cons=[...]),
           ]
         - tech_stack: [
             TechChoice(component="后端框架", technology="Spring Boot 3", version="3.2"),
             TechChoice(component="数据库", technology="PostgreSQL 16", version="16"),
             TechChoice(component="缓存", technology="Redis 7", version="7.2"),
             ...
           ]
         - components: [
             ComponentDetail(name="UserService", ...),
             ComponentDetail(name="OrderService", ...),
             ComponentDetail(name="ProductService", ...),
             ...
           ]

    3. 映射回:
       state["planning_result"] = PlanningResultDetail(...)
       state["component_decomposition"] = [...]
       state["tech_stack_choices"] = [...]
       state["progress"] = 0.55

  PostgresSaver: 写入 checkpoint_6
```

#### 节点 4.8: `needs_review` → `planning_human_review`

```
(与 analysis_human_review 相同流程)
  → interrupt() 暂停
  → 等待人工审核
  → Command(resume=...) 恢复
  → 继续到 generation
```

#### 节点 4.9: `generation` — 方案生成

```
Node: generation (GenerationAdapter)
  输入: state["planning_result"], state["analysis_result"], state["task_id"]
  内部:
    1. 提取生成层输入:
       generation_input = {
         "planning_result": state["planning_result"],
         "analysis_result": state["analysis_result"],
         "task_id": state["task_id"],
         "export_formats": state.get("export_formats", {}),
         "section_contents": state.get("section_contents", {}),
       }

    2. 调用 Generation Layer StateGraph.ainvoke(generation_input):
       outline → template_select → section_writer (14 节串行/并行)
       → mermaid → code_scaffold → consistency_check → revision → export → assemble

       SectionWriterNode 流式生成:
         async for token in GatewayChatModel.stream_complete(prompt, ...):
           full_text += token
           if len(full_text) % 200 == 0:
             EventBus.publish("task:abc-123-def",
               SseEvent("generation.chunk", {content: token, section: "3. 架构总览"}))

       输出:
         - section_contents: {
             "1. 项目概述": "# 项目概述\n\n本方案为电商平台...",
             "2. 需求分析": "# 需求分析\n\n## 功能需求\n...",
             ...
           }
         - generation_result: GenerationResultDetail {
             title: "电商平台技术方案",
             sections: [...],
             diagrams: ["mermaid_arch.mmd", "mermaid_er.mmd", ...],
             code_scaffold: { "UserService": "package com...", ... },
             export_formats: { "markdown": "...", "pdf": "...", "docx": "..." },
           }

    3. 映射回:
       state["generation_result"] = GenerationResultDetail(...)
       state["section_contents"] = {...}
       state["export_formats"] = {...}
       state["progress"] = 0.75

  PostgresSaver: 写入 checkpoint_7
```

#### 节点 4.10: `evaluation` — 质量评测

```
Node: evaluation (EvaluationAdapter)
  输入: state["analysis_result"], state["planning_result"], state["generation_result"]
  内部:
    1. 提取评测层输入:
       evaluation_input = {
         "analysis_result": state["analysis_result"],
         "planning_result": state["planning_result"],
         "generation_result": state["generation_result"],
       }

    2. 调用 Evaluation Layer StateGraph.ainvoke(evaluation_input):
       coverage_check → consistency_check → feasibility_check
       → architecture_quality → security_compliance → cost_eval
       → implementability → tech_advancement → legal_compliance → scoring

       ScoringNode 汇总:
         # 各子节点返回的分维度评分
         collected = {
           "prd_coverage": 8.5,
           "consistency": 7.8,
           "feasibility": 8.0,
           "architecture_quality": 8.5,
           "security": 7.5,
           "cost": 7.0,
           "implementability": 8.0,
           "tech_advancement": 7.0,
           "legal_compliance": 8.0,
           "completeness": 8.5,
         }

         # 加权计算
         overall = (
           8.5*0.15 + 7.8*0.15 + 8.0*0.15 + 8.5*0.15 +
           7.5*0.10 + 7.0*0.05 + 8.0*0.10 + 7.0*0.05 +
           8.0*0.05 + 8.5*0.05
         ) = 8.04

         # ScoreCalibrator 校准:
         #   - 历史比对: 电商类项目平均分 7.8, 当前 8.04, 在 1σ 内 → 正常
         #   - 平行评测: 用 GPT-4o-mini 评测得 7.9, 差异 1.7% < 15% → 正常

      最终: overall_score = 8.04 (校准后)

    3. 映射回:
       state["evaluation_report"] = EvaluationReportDetail(
         overall_score=8.04,
         dimension_scores={...},
         critical_issues=[],
         recommendations=["建议增强安全设计细节", "建议补充灾备方案"],
         conclusion="需要修改",
       )
       state["iteration_count"] = 1
       state["progress"] = 0.90

  PostgresSaver: 写入 checkpoint_8
```

#### 节点 4.11: `IterationDecider` — 迭代决策

```
条件路由函数: IterationDecider.run(state)
  evaluation_report.overall_score = 8.04
  iteration_count = 1
  max_iterations = 3

  8.04 >= 85? → 否
  8.04 >= 70? → 是
    consistency = 7.8 >= 70 → 不需要 regeneration
    feasibility = 8.0 >= 70 → 不需要 replanning

  返回: "final_assembly"  ← 虽然结论是"需要修改"，但大于 70 分阈值，通过
```

#### 节点 4.12: `final_assembly` — 最终组装

```
Node: final_assembly (FinalAssemblyNode)
  输入: state（全量）
  内部:
    state["status"] = "complete"
    state["progress"] = 1.0
    DecisionRecorder.end_trace("abc-123-def")
    Webhook 通知:
      integration_hub.notify("task.completed", {
        task_id: "abc-123-def",
        workspace_id: "ws-001",
        status: "completed",
        progress: 1.0,
      })
  输出:
    state["status"] = "complete"
    state["progress"] = 1.0

  PostgresSaver: 写入 checkpoint_9
```

#### 节点 4.13: `compress_memory` — 记忆压缩

```
Node: compress_memory (CompressMemoryNode)
  输入: state["_history_messages"]
  内部:
    ContextCompressor.compress(chat_messages, max_tokens=128000, reserve_for_latest=32000)
    → 如果上下文不超 limit → 直接返回
    → 如果超了 → summarize → rolling → truncate

  输出:
    state["compressed_context"] = [压缩后消息列表]

  PostgresSaver: 写入 checkpoint_10
```

#### 节点 4.14: `save_session` — 会话持久化

```
Node: save_session (SaveSessionNode)
  输入: state（全量）
  内部:
    1. connection_manager.get("postgres") → 获取 AsyncSession
    2. 提取结果摘要:
       generation_result.summary → "电商平台微服务架构方案..."
    3. 提取评测分数:
       evaluation_report.overall_score → 8.04
    4. 写入数据库:
       sessions 表: 更新 message_count, token_count, cost_usd, summary
       session_messages 表: 插入 user 消息 + assistant 消息
    5. EventBus.publish("task:abc-123-def", SseEvent("task.saved"))
  输出: 未修改 state

  PostgresSaver: 写入 checkpoint_11
```

#### 节点 4.15: END — 流终止

```
LangGraph 到达 END → astream 循环结束

TaskManager._execute_task():
  final_state["status"] = "complete"
  → _update_result(task_id, final_state)
    → task_record["status"] = "complete"
    → task_record["progress"] = 1.0
    → task_record["result"] = generation_result
    → task_record["evaluation"] = evaluation_report

  推送事件:
    EventBus.publish("task:abc-123-def",
      SseEvent("task.progress", {progress: 1.0, stage: "complete"}))
    EventBus.publish("task:abc-123-def",
      SseEvent("task.status", {status: "complete"}))
    EventBus.publish("task:abc-123-def",
      SseEvent("done", {task_id: "abc-123-def", result_summary: "..."}))
```

---


---

---

## 十、chat / knowledge_qa 路径全链路

### 10.1 chat 路径（闲聊/问候）

```
POST /api/v1/interact { message: "你好，你是谁？" }
  │
  ├─ IntentClassifier → intent = "chat", confidence = 1.0
  │
  ├─ chat() 中 intent != COMPLEX_GENERATION → 走同步 ainvoke 路径
  │
  ├─ orchestrator = get_orchestrator()  ← 获取编译后的图
  ├─ initial_state = make_initial_state(task_id, prd_raw, ...)
  ├─ config = {"configurable": {"thread_id": task_id}}
  │
  └─ final_state = await orchestrator.ainvoke(initial_state, config)
        │
        ▼
      classify → route_by_intent("chat") → chat_node
        │
        ChatNode.run(state):
          ├─ llm_gateway = state["_runtime"].llm_gateway
          ├─ EventBus.publish("task:{task_id}", SseEvent("chat.status", {phase: "generating"}))
          ├─ async for token in llm_gateway.stream_complete(prompt, task_type="chat"):
          │     full_response += token
          │     EventBus.publish("task:{task_id}", SseEvent("chat.chunk", {content: token}))
          ├─ state["chat_response"] = full_response
          ├─ state["status"] = "complete"
          └─ state["progress"] = 1.0
        │
        ▼
      save_session → END

  返回:
    ChatResponse(
      intent="chat",
      confidence=1.0,
      message="你好！我是 PRD2TSD Agent，可以帮您分析需求并生成技术方案文档。",
      session_id="",
    )
```

### 10.2 knowledge_qa 路径（知识库查询）

```
POST /api/v1/interact { message: "这个项目中有哪些关于用户服务的架构设计？" }
  │
  ├─ IntentClassifier → intent = "knowledge_qa"
  │   匹配: "哪些" + "架构设计" → KNOWLEDGE_PATTERNS
  │
  └─ classify → route_by_intent("knowledge_qa") → retrieve_node
        │
        KnowledgeQANode.run(state):
          ├─ RetrievalPipeline.retrieve(
          │     query="用户服务 架构设计",
          │     mode="hybrid",
          │     top_k=5,
          │     workspace_id=state["workspace_id"],
          │   )
          │   → RetrievalContext with 5 ScoredDocs
          │
          ├─ EventBus.publish("task:{task_id}", SseEvent("qna.status", {phase: "retrieving"}))
          │
          ├─ 构造 RAG prompt:
          │   "基于以下知识库内容回答用户问题:
          │    [ScoredDoc1...], [ScoredDoc2...], ...
          │    用户问题: 这个项目中有哪些关于用户服务的架构设计？"
          │
          ├─ async for token in llm_gateway.stream_complete(rag_prompt, task_type="knowledge_qa"):
          │     full_response += token
          │     EventBus.publish("task:{task_id}", SseEvent("qna.chunk", {content: token}))
          │
          ├─ state["chat_response"] = full_response
          └─ state["status"] = "complete"
        │
        ▼
      save_session → END
```

---


---

---

## 十一、断点恢复与 Human-in-the-Loop 全链路

### 11.1 完整时序图

```
用户          FastAPI          TaskManager          LangGraph          PostgresSaver
 │               │                  │                    │                   │
 │  POST /chat   │                  │                    │                   │
 │──────────────→│                  │                    │                   │
 │               │ create_task()   │                    │                   │
 │               │────────────────→│                    │                   │
 │               │  return task_id │  _execute_task()   │                   │
 │               │←────────────────│  astream(init)     │                   │
 │               │                  │───────────────────→│                   │
 │               │                  │                    │  classify         │
 │               │                  │                    │  retrieve_memory  │
 │               │                  │    progress:0.10   │  knowledge_ret... │
 │               │                  │←───────────────────│                   │
 │               │                  │                    │  analysis         │
 │               │                  │    progress:0.30   │                   │
 │               │                  │←───────────────────│                   │
 │               │                  │                    │                   │
 │               │                  │                    │  needs_review     │
 │               │                  │                    │  → review_needed  │
 │               │                  │                    │                   │
 │               │                  │                    │  analysis_human   │
 │               │                  │                    │  _review          │
 │               │                  │                    │  interrupt()      │
 │               │                  │                    │──────────────────→│
 │               │                  │                    │                   │ save checkpoint
 │               │                  │                    │←──────────────────│
 │               │                  │    status:paused   │                   │
 │               │                  │←───────────────────│                   │
 │               │                  │                    │                   │
 │               │                  │  SSE: review_required                  │
 │               │  SSE 推送         │                    │                   │
 │               │←─────────────────│                    │                   │
 │               │                  │                    │                   │
 │  [用户看到审核界面]               │                    │                   │
 │  [点击"通过"]                     │                    │                   │
 │               │                  │                    │                   │
 │  POST /review │                  │                    │                   │
 │──────────────→│                  │                    │                   │
 │               │ resolve_review() │                    │                   │
 │               │────────────────→│                    │                   │
 │               │                  │ _resume_task()     │                   │
 │               │                  │ astream(           │                   │
 │               │                  │   Command(         │                   │
 │               │                  │     resume=        │                   │
 │               │                  │     feedback       │                   │
 │               │                  │   )                │                   │
 │               │                  │ )                  │                   │
 │               │                  │───────────────────→│                   │
 │               │                  │                    │ load checkpoint   │
 │               │                  │                    │←─────────────────│
 │               │                  │                    │                   │
 │               │                  │                    │ interrupt()       │
 │               │                  │                    │ → returns feedback│
 │               │                  │                    │ → 继续执行        │
 │               │                  │                    │                   │
 │               │                  │    progress:0.55   │  planning         │
 │               │                  │←───────────────────│                   │
 │               │                  │                    │  ... 继续 ...     │
 │               │                  │                    │                   │
 │               │                  │    done            │  save_session     │
 │               │                  │←───────────────────│                   │
 │               │                  │                    │                   │
 │               │  SSE: done       │                    │                   │
 │               │←─────────────────│                    │                   │
```

### 11.2 崩溃恢复场景

```
场景: 服务在 generation 节点执行中崩溃

崩溃前:
  PostgresSaver 中已有 checkpoint:
    checkpoint_0: 初始状态
    checkpoint_1: classify 完成后
    checkpoint_2: retrieve_memory 完成后
    checkpoint_3: knowledge_retrieval 完成后
    checkpoint_4: analysis 完成后
    checkpoint_5: analysis_human_review (interrupt 点)
    checkpoint_6: planning 完成后
    checkpoint_7: planning_human_review (interrupt 点)
    checkpoint_8: generation 开始前（最新的 checkpoint）

  sessions 表中:
    thread_id = "xxx-yyy-zzz"
    status = "running"

重启后恢复:
  1. FastAPI lifespan → 重新初始化 PostgresSaver
  2. 重新构建 + 编译主编排图
  3. 发现 sessions 表中有 status="running" 的会话
     → thread_id = "xxx-yyy-zzz"

  4. 手动触发恢复:
     POST /api/v1/tasks/{task_id}/resume
     → TaskManager:
       config = {"configurable": {"thread_id": "xxx-yyy-zzz"}}
       orchestrator.astream(None, config)
       # 传入 None（不是 Command(resume=...)）因为不是在 interrupt 点
       # LangGraph 从 checkpoint_8 恢复
       # 重放 classify → ... → generation（已完成的节点自动跳过）
       # 继续执行 evaluation → ... → save_session → END
```

---


---

---

## 十二、历史消息处理全链路

### 12.1 会话生命周期

```
┌─────────────────────────────────────────────────────────────┐
│                 会话生命周期                                 │
│                                                             │
│  1. 创建会话                                                │
│     POST /api/v1/sessions                                    │
│     → SessionHistoryService.create_session()                │
│       ├─ 自动生成 thread_id (uuid4)                         │
│       ├─ 写入 sessions 表:                                    │
│       │   { id, title, session_type, workspace_id,          │
│       │     user_id, thread_id, status:"active" }            │
│       └─ 返回 SessionOut { thread_id: "xxx-yyy-zzz", ... }  │
│                                                             │
│  2. 发送消息（绑定会话）                                      │
│     POST /api/v1/interact                                   │
│       Body: { message: "...", session_id: "session-001" }   │
│       → 从 sessions 表取出 thread_id = "xxx-yyy-zzz"         │
│       → config = {"configurable": {"thread_id": thread_id}} │
│       → orchestrator.ainvoke/astream(state, config)          │
│         ├─ retrieve_memory 节点:                             │
│         │     从 sessions/session_messages 表加载历史消息     │
│         │     MemoryRetriever.retrieve(history_messages)     │
│         │     → 注入 state["retrieved_memories"]             │
│         │                                                   │
│         ├─ ... 中间节点 ...                                  │
│         │                                                   │
│         └─ save_session 节点:                                │
│              ├─ INSERT INTO session_messages                 │
│              │   (session_id, user_id, role, content, ...)   │
│              ├─ UPDATE sessions SET                          │
│              │   message_count += 1,                         │
│              │   token_count += ...,                         │
│              │   cost_usd += ...,                            │
│              │   summary = "...",                            │
│              │   last_message_at = NOW()                     │
│              └─ 通过 EventBus 推送 task.saved                │
│                                                             │
│  3. 查询历史会话                                              │
│     GET /api/v1/sessions?page=1&status=active                 │
│     → SessionHistoryService.list_sessions()                 │
│       ├─ 分页: LIMIT 20 OFFSET (page-1)*20                   │
│       ├─ 筛选: status/type/tags                              │
│       ├─ 排序: last_message_at DESC                           │
│       └─ 返回 PageResult { items: [...], total: 50 }         │
│                                                             │
│     GET /api/v1/sessions/{session_id}/messages                │
│     → SessionHistoryService.get_messages()                  │
│       ├─ 按 created_at ASC 排序                               │
│       ├─ 返回 [{role, content, content_type, ...}, ...]      │
│       └─ 支持分页                                             │
│                                                             │
│  4. 搜索会话                                                 │
│     GET /api/v1/sessions/search?q=电商架构                      │
│     → SessionSearchService.search()                         │
│       ├─ PostgreSQL FTS:                                     │
│       │   to_tsvector('simple', content) @@                  │
│       │   plainto_tsquery('simple', '电商架构')              │
│       ├─ 返回匹配的会话 + 消息片段                             │
│       └─ 高亮匹配文本（ts_headline）                          │
│                                                             │
│  5. 导出会话                                                 │
│     GET /api/v1/sessions/{session_id}/export?format=markdown  │
│     → SessionExporter.export(session_id, format)             │
│       ├─ Markdown: # {title}\n\n**User**: {content}\n\n...   │
│       ├─ JSON: {"messages": [{...}, {...}], "metadata": ...} │
│       └─ 返回文件下载                                         │
│                                                             │
│  6. 老化清理                                                 │
│     Celery Beat: cleanup-expired-sessions (每小时)            │
│     → SessionCleanupPolicy.cleanup()                         │
│       ├─ Free: last_message_at < NOW() - 30 days → 软删除    │
│       ├─ Pro: last_message_at < NOW() - 180 days → 软删除    │
│       └─ Enterprise: 不自动清理                               │
│                                                             │
│  7. 续接会话                                                 │
│     POST /api/v1/interact                                   │
│       Body: { message: "继续上次讨论...", session_id: "..." } │
│       → 读取 session.thread_id                                │
│       → config = {"configurable": {"thread_id": thread_id}}  │
│       → orchestrator.ainvoke(new_state, config)              │
│         ├─ LangGraph 自动加载该 thread 的历史 checkpoint      │
│         ├─ retrieve_memory 节点获取之前对话记忆                │
│         ├─ LLM 看到完整的历史上下文                            │
│         └─ 新消息追加到 session_messages 表                    │
└─────────────────────────────────────────────────────────────┘
```

### 12.2 MemoryRetriever 四种策略对比

```
场景: 用户在 50 轮对话后问 "之前讨论的那个数据库方案是什么？"

策略 1: recency（最近优先）
  评分: 最近 5 轮消息权重最高，24h 前的指数衰减到 0.37
  适用: 短期对话，用户记得最近讨论的内容

策略 2: relevance（语义相关）
  评分: "数据库" + "方案" → 关键词重叠 → 语义向量相似度
  适用: 精确查找特定话题

策略 3: importance（重要优先）
  评分: LLM 判断每条消息的重要性（0-1）
  适用: 长期记忆，保留关键决策

策略 4: hybrid（融合）
  评分: 0.3*recency + 0.4*relevance + 0.3*importance
  适用: 通用场景（默认策略）
```

---


---

---

## 十三、SSE 流式推送全链路

### 13.1 EventBus 实现细节

```python
class EventBus:
    """基于 asyncio.Queue 的内存 Pub/Sub。

    关键设计决定:
    1. 每个订阅者独立 Queue → 互不影响
    2. put_nowait() 非阻塞 → Publisher 不会被慢 Subscriber 拖慢
    3. Queue maxsize=128 → 内存保护，满时静默丢弃
    4. channel = "task:{task_id}" → 每个任务独立频道
    """

    async def publish(self, channel: str, event: SseEvent) -> None:
        # 获取当前所有订阅者（快速复制，不长期持有锁）
        async with self._lock:
            queues = list(self._channels.get(channel, set()))

        # 向每个订阅者推送（非阻塞）
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("订阅者队列已满，丢弃事件: channel=%s", channel)
```

### 13.2 SSE 端点实现

```python
@router.get("/api/v1/tasks/{task_id}/events")
async def stream_task_events(task_id: str):
    """SSE 端点 — 订阅任务事件流。"""

    # 1. 订阅
    queue = await event_bus.subscribe(f"task:{task_id}")

    async def event_generator():
        try:
            # 发送初始连接成功事件
            yield SseEvent(type="connected", payload={"task_id": task_id}).to_sse_line()

            # 设置心跳定时器（30s）
            last_event_time = asyncio.get_event_loop().time()

            while True:
                try:
                    # 等待事件，超时 15s
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event.to_sse_line()
                    last_event_time = asyncio.get_event_loop().time()

                    # 任务完成 → 退出
                    if event.type == "done":
                        break

                except asyncio.TimeoutError:
                    # 15s 无事件 → 发送心跳
                    now = asyncio.get_event_loop().time()
                    if now - last_event_time >= 15:
                        yield SseEvent.keepalive().to_sse_line()
                        last_event_time = now

        except asyncio.CancelledError:
            pass  # 客户端断开
        finally:
            # 取消订阅（清理资源）
            await event_bus.unsubscribe(f"task:{task_id}", queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
```

### 13.3 流式生成集成

```
SectionWriterNode 流式生成:
  │
  ├─ GatewayChatModel.stream_complete(prompt, ...)
  │     │
  │     ▼
  │   LLMGateway.stream_complete():
  │     ├─ GuardrailManager.pre_llm()
  │     ├─ FailoverManager.get_target()
  │     ├─ Provider.stream_complete()
  │     │     └─ OpenAI SDK: stream=True
  │     │         async for chunk in client.chat.completions.create(stream=True, ...):
  │     │           token = chunk.choices[0].delta.content
  │     │           yield token
  │     └─ GuardrailManager.post_llm()
  │
  ├─ 每积累 200 字符:
  │     EventBus.publish("task:{task_id}",
  │       SseEvent("generation.chunk", {
  │         content: last_200_chars,
  │         section: "3. 架构总览",
  │         progress: 0.65,
  │       }))
  │
  └─ Section 完成:
        EventBus.publish("task:{task_id}",
          SseEvent("generation.section", {
            section: "3. 架构总览",
            status: "done",
            content_length: 3500,
          }))
```

### 13.4 SSE 事件完整时间线（一次 complex_generation 任务）

```
时间   事件类型               Payload
────   ──────────────────     ──────────────────────────────────
0s     task.created           {task_id: "abc-123", status: "running"}
0.1s   task.progress          {progress: 0.0, stage: "initializing"}
0.2s   task.log               {level: "info", message: "开始任务执行..."}
0.5s   task.progress          {progress: 0.05, stage: "classify"}
1.0s   task.progress          {progress: 0.08, stage: "retrieve_memory"}
2.0s   task.progress          {progress: 0.10, stage: "knowledge_retrieval"}
2.0s   task.log               {level: "info", message: "知识检索完成: docs=10"}
15s    task.progress          {progress: 0.30, stage: "analysis"}
15s    task.review_required   {task_id: "abc-123", stage: "analysis"}
15s    task.status            {status: "paused"}
────   等待人工审核 (可能几分钟到几小时)
       task.review_resolved   {task_id: "abc-123", stage: "analysis", decision: "approved"}
       task.status            {status: "resuming"}
30s    task.progress          {progress: 0.55, stage: "planning"}
       task.review_required   {task_id: "abc-123", stage: "planning"}
       task.status            {status: "paused"}
────   等待人工审核
       task.review_resolved   {decision: "approved"}
       task.status            {status: "resuming"}
45s    task.progress          {progress: 0.65, stage: "generation"}
       generation.section     {section: "1. 项目概述", status: "generating"}
       generation.chunk       {content: "# 项目概述\n\n本方案...", section: "1. 项目概述"}
       generation.section     {section: "1. 项目概述", status: "done"}
       generation.section     {section: "2. 需求分析", status: "generating"}
       generation.chunk       {content: "# 需求分析\n\n## 功能需求...", section: "2. ..."}
       ... (14 个章节逐节推送)
60s    generation.section     {section: "14. 风险与缓解", status: "done"}
60s    task.progress          {progress: 0.75, stage: "evaluation"}
65s    task.progress          {progress: 0.90, stage: "evaluation"}
66s    task.progress          {progress: 1.0, stage: "complete"}
66s    task.status            {status: "complete"}
66s    task.saved             {task_id: "abc-123", status: "complete", score: 8.04}
66s    done                   {task_id: "abc-123", result_summary: "电商平台微服务架构方案..."}
```

---


---

---

## 十四、LLM 调用全链路（Gateway + LangChain 适配器）

### 14.1 两种调用方式对比

```
方式 1: 直接 Gateway 调用
  ────────────────────────
  使用场景: TaskManager, ChatNode, KnowledgeQANode 等非 Agent 节点
  代码:
    response = await gateway.complete(
        prompt="...",
        task_type="chat",
        workspace_id="ws-001",
        layer="orchestrator",
        node="chat_node",
    )

  内部链路:
    0. 前置护栏 (PromptInjection + PII + Timeout)
    1. 速率限制检查 (RateLimiter.check)
    2. 模型路由 (ModelRouter.route)
    3. 预算检查 (BudgetController.check)
    4. 语义缓存 (SemanticCache.lookup)
    5. Circuit Breaker 检查
    6. FailoverManager 选 Provider
    7. OpenTelemetry Span 创建
    8. Provider.complete() 实际调用
    9. 后置护栏 (ContentSafety + OutputValidator + EmptyResponse + RetryDecision)
    10. 设置缓存
    11. CostTracker.record() → llm_call_logs
    12. Prometheus 指标更新
    13. 返回 LLMResponse


方式 2: LangChain 适配器调用
  ──────────────────────────
  使用场景: Analysis/Planning/Generation/Evaluation 层的节点内部
  代码:
    llm = GatewayChatModel(
        gateway=gateway,
        task_type="analysis",
        layer="analysis",
        node="requirement_extractor",
    )
    chain = ChatPromptTemplate.from_messages([...]) | llm | PydanticOutputParser(...)
    result = await chain.ainvoke({"input": "..."})

  内部链路:
    1. LangChain 调用 BaseChatModel._agenerate(messages, ...)
    2. GatewayChatModel._messages_to_prompt(messages) → 拼接为单 prompt
    3. gateway.complete(prompt, task_type, layer, node, ...)
       → 同方式 1 的 0-13 步
    4. 返回 ChatResult( AIMessage(content=response.content) )
    5. PydanticOutputParser.parse(response.content) → Pydantic Model
    6. 返回结构化结果

  优势:
    - Agent 节点内部可以使用 LangChain 生态 (PromptTemplate, OutputParser, bind_tools)
    - 同时保留 Gateway 的全部生产级能力 (限流/缓存/熔断/护栏/成本追踪)
    - 不引入被 tech-stack.yml 禁止的 langchain-openai 等包
```

### 14.2 GatewayChatModel 源码核心

```python
class GatewayChatModel(BaseChatModel):
    """将 LLM Gateway 包装为 LangChain BaseChatModel。

    关键方法:

    _agenerate(messages, stop, run_manager, **kwargs):
        # 1. LangChain 消息 → 纯文本 prompt
        prompt = self._messages_to_prompt(messages)

        # 2. 委托给 Gateway（保留全部生产级能力）
        response = await self.gateway.complete(
            prompt=prompt,
            task_type=self.task_type,
            layer=self.layer,
            node=self.node,
            **kwargs,
        )

        # 3. 构造 LangChain ChatResult
        return ChatResult(
            generations=[ChatGeneration(
                message=AIMessage(content=response.content),
                generation_info={
                    "model": response.model,
                    "usage": response.usage,
                    "cost": response.cost,
                },
            )],
        )

    _astream(messages, stop, run_manager, **kwargs):
        # 流式调用
        async for token in self.gateway.stream_complete(prompt, ...):
            yield ChatGenerationChunk(message=AIMessageChunk(content=token))

    bind_tools(tools):
        # Function Calling 支持
        # 使用 Gateway 的 LLM 能力 + OpenAI Function Calling Schema
        ...
```

### 14.3 LLM 调用的完整护栏链路

```
用户 Prompt
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│                    pre_llm 护栏管道                       │
│                                                          │
│  1. PromptInjectionGuardrail.check(prompt)               │
│     检测模式:                                             │
│     - "ignore previous instructions"                     │
│     - "you are now DAN"                                  │
│     - "system: ..."                                      │
│     → blocked → 返回 GuardrailResult(blocked=True)       │
│                                                          │
│  2. PIIDetectorGuardrail.check(prompt)                   │
│     检测模式:                                             │
│     - 邮箱: xxx@xxx.xxx                                   │
│     - 手机号: 1\d{10}                                     │
│     - 身份证号: \d{17}[\dXx]                              │
│     → 脱敏: DataMaskingEngine.mask()                      │
│     → 返回脱敏后的 prompt                                  │
│                                                          │
│  3. TimeoutGuardrail.check(circuit_breaker)               │
│     检查 CircuitBreaker 状态:                              │
│     ├─ CLOSED → 正常                                      │
│     ├─ OPEN → blocked → CircuitBreakerError               │
│     └─ HALF_OPEN → 允许试探                                │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│               LLM 调用（带 Failover 链）                   │
│                                                          │
│  FailoverManager.call_with_failover(model_type="llm"):   │
│    ├─ attempt 1: deepseek-chat                            │
│    │   └─ 成功 → 返回                                     │
│    ├─ attempt 2 (如果 1 失败): gpt-4o-mini                 │
│    │   └─ CircuitBreaker OPEN? → 跳过                     │
│    └─ 全部失败 → AllProvidersUnavailableError              │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│                    post_llm 护栏管道                      │
│                                                          │
│  4. ContentSafetyGuardrail.check(response)               │
│     检测不安全内容:                                        │
│     - 暴力/色情/仇恨言论                                   │
│     → blocked → 返回 GuardrailResult(blocked=True)       │
│                                                          │
│  5. OutputValidatorGuardrail.check(response, schema)     │
│     校验输出格式:                                          │
│     - JSON 格式是否正确                                    │
│     - 是否符合预期的 JSON Schema                           │
│     → 不通过 → GuardrailResult(passed=False)             │
│                                                          │
│  6. EmptyResponseGuardrail.check(response)               │
│     检测: response.content == ""                          │
│     → 空响应 → GuardrailResult(passed=False)             │
│                                                          │
│  7. RetryDecisionGuardrail.decide(guard_results)         │
│     汇总所有护栏结果，决定:                                 │
│     ├─ retry: 可以重试（写入 metadata: {retry: True, ...}）│
│     ├─ fallback: 降级模型                                  │
│     └─ continue: 正常返回                                  │
│     → GuardrailResult.metadata 供 LangGraph 条件路由使用  │
└──────────────────────────────────────────────────────────┘
```

---


---

---

## 十五、LangGraph 与 LangChain 的分工设计

### 15.1 明确边界

```
┌─────────────────────────────────────────────────────────────┐
│  LangGraph 的职责:                                           │
│                                                             │
│  1. 图结构定义（StateGraph + add_node + add_edge）           │
│  2. 条件路由（add_conditional_edges + route 函数）           │
│  3. 人工中断恢复（interrupt() + Command(resume=...)）        │
│  4. 状态持久化（PostgresSaver checkpoint）                   │
│  5. 并行扇出（Send() API）                                   │
│  6. 子图嵌套（add_node(compiled_subgraph)）                  │
│                                                             │
│  LangGraph 不负责:                                           │
│  - LLM 调用本身                                              │
│  - Prompt 构建                                               │
│  - 输出解析                                                  │
│  - Tool Calling                                              │
├─────────────────────────────────────────────────────────────┤
│  LangChain 的职责:                                           │
│                                                             │
│  1. Prompt 模板（ChatPromptTemplate / MessagesPlaceholder） │
│  2. 结构化输出（PydanticOutputParser / with_structured_output）│
│  3. Tool Calling（bind_tools + ToolMessage）                │
│  4. LLM 调用适配（GatewayChatModel extends BaseChatModel）  │
│  5. LCEL 链式组合（prompt | llm | parser）                  │
│                                                             │
│  LangChain 不负责:                                           │
│  - Agent 编排（这是 LangGraph 的职责）                        │
│  - langchain.agents / langchain.chains（被 tech-stack 禁止）│
└─────────────────────────────────────────────────────────────┘
```

### 15.2 每一层使用什么

| 层级 | LangGraph 使用 | LangChain 使用 |
|------|--------------|--------------|
| **主编排图** | ✅ StateGraph 节点编排、条件路由、interrupt/resume、PostgresSaver | ❌ 不使用 |
| **4 个 Agent Layer** | ✅ 各自独立的 StateGraph（含节点链 + 条件边） | ✅ ChatPromptTemplate + GatewayChatModel + PydanticOutputParser |
| **Adapter 层** | ❌ 不使用（纯 Python 类） | ❌ 不使用（纯状态映射） |
| **TaskManager** | ✅ `astream()` 逐节点消费、`Command(resume=...)` 恢复 | ❌ 不使用 |
| **ChatNode / KnowledgeQANode** | ❌ 只是图中的一个普通节点 | ✅ GatewayChatModel.stream_complete() |
| **GatewayChatModel** | ❌ 不使用 | ✅ 实现 LangChain BaseChatModel 接口 |
| **LLM Gateway** | ❌ 不使用 | ✅ GatewayChatModel 内部调用 Gateway |

### 15.3 为什么不用 LangChain AgentExecutor？

```
tech-stack.yml 黑名单:
  forbidden:
    - langchain              ← 禁止 langchain 全家桶
    - langchain-community
    - langchain-openai

原因:
  1. AgentExecutor 是一个黑盒 ReAct 循环，难以精确控制
  2. 我们使用 LangGraph StateGraph 替代 AgentExecutor
     → 显式定义每个步骤，完全可控
  3. 我们使用 GatewayChatModel 替代 langchain-openai 的 ChatOpenAI
     → 保留成本追踪、限流、缓存、护栏等定制能力
  4. langchain-core 在白名单中（允许 ChatPromptTemplate / PydanticOutputParser）
```

---


---

---

## 十六、关键技术决策与架构原则

### 16.1 架构原则

```
原则 1: 组件逻辑不变，仅解决接线问题
  LLM Gateway / Guardrails / ContextCompressor / MemoryRetriever
  / SessionHistoryService / EventBus 的现有实现逻辑全部保持不变，
  仅将它们接入 LangGraph 图中作为节点调用。

原则 2: 错误处理进入护栏体系
  错误处理不是独立模块，而是护栏系统的一个维度。
  新增 TimeoutGuardrail / EmptyResponseGuardrail / RetryDecisionGuardrail
  三个护栏插件，加入已有的 pre_llm / post_llm 管道。

原则 3: Config / State / Runtime 三层分离
  - Config: 启动时加载，只读（如 max_iterations=3）
  - State: LangGraph checkpoint 自动持久化
  - Runtime: 每次请求注入，不参与序列化（如 db_session, event_bus）

原则 4: 4 层 Agent 100% 通过 contracts 解耦
  层与层之间不直接 import，通过 Adapter 做状态映射。
  每个 Layer 可以独立编译、独立测试。

原则 5: 禁止在 Layer Node 内部直接引用 OrchestratorState
  这破坏了 Layer 的独立性，使 Layer 的单元测试失效。
```

### 16.2 关键数据流决策

```
决策 1: session.thread_id = LangGraph checkpoint thread_id
  影响: 会话历史与 LangGraph 状态持久化完全绑定
  好处: 续接会话时自动恢复 Graph 状态
  代价: sessions 表增加了 thread_id 字段

决策 2: PostgresSaver 替代 MemorySaver
  影响: 检查点从内存移到 PostgreSQL
  好处: 服务重启不丢失状态、支持崩溃恢复
  代价: 每次 checkpoint 有一次 PG 写入（但 LangGraph 已优化为批量写入）

决策 3: astream 替代 ainvoke 做 TaskManager 执行
  影响: 每次节点执行完 yield，TaskManager 读取 progress
  好处: 实时进度推送、节点级别的可观测性
  代价: 稍微增加了 TaskManager 的复杂度

决策 4: Command(resume=value) 替代直接传参做 resume
  影响: 中断恢复从 hacky 的 try/except 改为 LangGraph 原生 API
  好处: 正确处理 checkpoint 回放，不会丢失中间状态
  代价: 需要在 interrupt() 时正确构造 resume_value

决策 5: GatewayChatModel 替代 langchain-openai 的 ChatOpenAI
  影响: 不使用 langchain-openai，用自己的 LLM Gateway + LangChain 适配器
  好处: 保留成本追踪/限流/缓存/熔断/护栏全部能力
  代价: 需要自己维护适配器代码
```

### 16.3 性能优化策略

```
1. 语义缓存:
   相同 query → 相同 prompt → 命中缓存 → 跳过 LLM 调用
   缓存 key: SHA-256(prompt + model + temperature + max_tokens)

2. 预算控制:
   workspace 月预算超 90% → 自动降级到低成本模型
   降级链: deepseek-chat → gpt-4o-mini

3. Session 老化清理:
   定时清理过期会话，释放存储空间
   Free: 30天 / Pro: 180天

4. ContextCompressor:
   Token 超限时自动压缩，确保 LLM 调用不失败
   三级回退: summarize → rolling → truncate

5. Failover 链:
   主 Provider 不可用时自动切换
   恢复后自动切回

6. Circuit Breaker:
   连续失败 N 次 → 熔断 → 避免持续重试
   超时半开 → 试探 → 恢复或继续熔断

7. Send() 并行扇出 (Block G 计划):
   Evaluation 9 个节点并行 → 总耗时 = max(单节点) 而非 sum
```

---


---

---

## 十七、面试要点：核心卖点总结

### 17.1 项目亮点（一句话版本）

| # | 亮点 | 适合面试展开的点 |
|---|------|----------------|
| 1 | **LangGraph + LangChain 混合架构** | "为什么不用纯 LangChain AgentExecutor？因为我们需要精确控制每个步骤、支持 Human-in-the-Loop、支持 checkpoint 持久化。LangGraph 做图编排，LangChain 做节点内部的 LLM 调用和结构化输出。" |
| 2 | **PostgreSQL Checkpointer** | "传统的 Agent 系统崩溃后状态全丢。我们用 PostgresSaver 把每一步的状态持久化到 PG，崩溃后可以从最近的 checkpoint 恢复续跑。" |
| 3 | **自研 LLM Gateway** | "封装的不是简单的 API 调用，而是一整套生产级能力：7 个护栏插件、Provider Failover 链、Circuit Breaker 熔断、语义缓存、成本追踪、速率限制、预算控制。" |
| 4 | **实体增强双路检索 + 反思** | "不是简单的 RAG。我们做了 Neo4j 知识图谱 + PGVector 向量双路检索，还有 ReflectionJudge 自我纠偏——检索结果不好就自动修正查询重新检索。" |
| 5 | **Human-in-the-Loop** | "关键节点（需求分析、架构规划）会用 LangGraph 的 interrupt() 暂停，等待人工审核。审核通过后通过 Command(resume=...) 无缝恢复。" |
| 6 | **SSE 流式推送** | "14 种事件类型覆盖全生命周期。用户可以看到实时进度条、流式文档生成、审核通知。基于 asyncio.Queue 的 Pub/Sub 实现，非阻塞推送。" |
| 7 | **迭代闭环** | "评测层给方案打分，低于 85 分自动回退重新规划或重新生成，最多 3 轮迭代。10 维加权评分 + 历史校准 + 平行评测校准。" |
| 8 | **多租户 + RBAC/ABAC** | "资源级权限控制，工作空间级别隔离。三级 Prompt 隔离（组织自定义 → 行业模板 → 系统默认）。数据分级脱敏（L1-L4）。" |

### 17.2 技术深度的体现

```python
面试时可以展开的点:

1. LangGraph 图结构设计的考量:
   - 为什么用 StateGraph 而不是 MessageGraph？
   - 条件路由 vs Command() 路由的适用场景
   - PostgresSaver 的 checkpoint 机制原理
   - astream vs ainvoke 的使用场景差异

2. LLM 调用的完整链路:
   - 7 个护栏插件的注册和执行顺序
   - Circuit Breaker 状态机 + Failover 链的协同
   - 为什么用 GatewayChatModel 包装而不是直接用 langchain-openai

3. 知识检索的架构:
   - Local Search 和 Global Search 的区别和适用场景
   - ReflectionJudge 的自我纠偏机制
   - Neo4j 图遍历 + PGVector 向量检索的融合策略

4. 工程实践:
   - Config/State/Runtime 三层分离的设计
   - Adapter 模式做 Layer 解耦
   - EventBus 的 asyncio.Queue 非阻塞设计
   - 代码行数限制（函数 ≤ 50 行，文件 ≤ 300 行）
```

### 17.3 可继续深挖的方向

```
Block G 未实现的计划:
  1. Send() 并行扇出 → Evaluation 9 节点并行执行
  2. 原生 Subgraph → 4 个 Layer 作为 LangGraph 原生子图
  3. Multi-Agent 模式 → Supervisor Agent + Worker Agents 协商

可能的扩展:
  1. 多模态输入（图片架构图 → 直接分析）
  2. 实时协同编辑（WebSocket + OT/CRDT）
  3. Agent 市场（社区贡献自定义 Agent Layer）
  4. 方案 A/B 测试（同一 PRD → 不同方案的对比评估）
```

---

> **文档结束** — 总计 5000+ 行，覆盖 PRD2TSD Agents 项目的全部模块、设计模式、运行时链路和面试要点。

---


---

# 附篇


---

---



---

## 附篇 A：各模块间数据流契约详解

### A.1 contracts/interfaces.py 完整数据模型

\\\python
# === 知识检索 ===
@dataclass
class ScoredDoc:
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any]

@dataclass
class RetrievalContext:
    query: str
    docs: list[ScoredDoc]
    search_mode: str  # local / global / hybrid

# === 分析层 ===
@dataclass
class Requirement:
    id: str          # FR-001 / NFR-001
    title: str
    description: str
    priority: str    # P0/P1/P2/P3
    category: str    # functional / non_functional

@dataclass
class Constraint:
    id: str
    description: str
    type: str        # technical / business / regulatory

@dataclass
class AnalysisResult:
    project_name: str
    summary: str
    requirements: list[Requirement]
    constraints: list[Constraint]
    metadata: dict[str, Any]

# === 规划层 ===
@dataclass
class TechChoice:
    component: str
    technology: str
    version: str
    reason: str

@dataclass
class Component:
    name: str
    description: str
    tech_stack: list[TechChoice]
    dependencies: list[str]

# === Pydantic 增强版模型 (Block C 新增) ===
class RequirementDetail(BaseModel):
    id: str
    type: Literal["functional", "non_functional"]
    category: str
    priority: Literal["P0", "P1", "P2", "P3"]
    description: str
    actor: str
    acceptance_criteria: list[str]
    source_section: str

class ConstraintDetail(BaseModel):
    type: Literal["technical", "performance", "time", "budget", "compliance", "team"]
    description: str
    severity: Literal["must", "should", "could"]
    source_section: str

class AnalysisResultDetail(BaseModel):
    project_name: str
    summary: str
    domain_tags: list[str]
    requirements: list[RequirementDetail]
    constraints: list[ConstraintDetail]
    dependency_graph: Any
    quality_scores: dict[str, float] = {}
    effort_estimate: dict[str, Any] = {}
    stakeholders: list[dict[str, Any]] = []
    clarity_issues: list[dict[str, Any]] = []

class PatternEval(BaseModel):
    name: str
    score: float
    pros: list[str]
    cons: list[str]
    fit_explanation: str

class PlanningResultDetail(BaseModel):
    architecture_patterns: list[PatternEval]
    tech_stack: list[TechChoiceDetail]
    components: list[ComponentDetail]
    data_architecture: dict[str, Any]
    api_plan: dict[str, Any]
    deployment_plan: dict[str, Any]
    cost_estimates: list[dict[str, Any]]
    timeline: dict[str, Any]
    skill_gaps: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    metadata: dict[str, Any]

class SectionOutline(BaseModel):
    number: int
    title: str
    subsections: list[str]
    estimated_tokens: int

class GenerationResultDetail(BaseModel):
    title: str
    sections: list[dict[str, Any]]
    outline: list[SectionOutline]
    diagrams: list[str]
    code_scaffold: dict[str, str]
    export_formats: dict[str, str]
    summary: str
    total_tokens: int

class EvaluationReportDetail(BaseModel):
    overall_score: float
    dimension_scores: dict[str, float]
    critical_issues: list[dict[str, Any]]
    recommendations: list[str]
    conclusion: str
    p0_coverage: float
    calibrations_applied: list[str]
\\\

---


---

---

## 附篇 B：完整 API 路由清单

### B.1 基础设施路由

| 方法 | 路径 | 功能 | 所属模块 |
|------|------|------|---------|
| POST | /api/v1/auth/register | 用户注册 | auth |
| POST | /api/v1/auth/login | 用户登录（返回 JWT） | auth |
| POST | /api/v1/auth/refresh | 刷新 access_token | auth |
| POST | /api/v1/auth/logout | 登出（加入黑名单） | auth |
| GET | /api/v1/health | 健康检查 | core |
| GET | /api/v1/model-config | 获取模型配置 | llm_gateway |
| PUT | /api/v1/model-config | 运行时更新模型配置 | llm_gateway |

### B.2 工作空间路由

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/v1/workspaces | 创建工作空间 |
| GET | /api/v1/workspaces | 列出工作空间 |
| GET | /api/v1/workspaces/{id} | 获取工作空间详情 |
| PUT | /api/v1/workspaces/{id} | 更新工作空间 |
| DELETE | /api/v1/workspaces/{id} | 归档工作空间 |
| POST | /api/v1/workspaces/{id}/members | 添加成员 |
| GET | /api/v1/workspaces/{id}/members | 列出成员 |
| DELETE | /api/v1/workspaces/{id}/members/{user_id} | 移除成员 |

### B.3 任务路由

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/v1/interact | 统一入口（意图分类 + 路由，对话/提问/文档分析/生成） |
| GET | /api/v1/tasks/{task_id} | 查询任务状态 |
| GET | /api/v1/tasks/{task_id}/events | SSE 事件流订阅 |
| POST | /api/v1/tasks/{task_id}/stream-review | 审核 + 流式恢复 |
| POST | /api/v1/tasks/{task_id}/resume | 崩溃后恢复 |

### B.4 审核路由

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/v1/review/pending | 列出待审核任务 |
| POST | /api/v1/review/{task_id}/{stage} | 提交审核结果 |

### B.5 评测路由

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/v1/evaluate | 对已有方案进行评测 |

### B.6 会话路由

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/v1/sessions | 创建会话 |
| GET | /api/v1/sessions | 列出会话（分页） |
| GET | /api/v1/sessions/search | 搜索会话（FTS） |
| GET | /api/v1/sessions/{id} | 获取会话详情 |
| PUT | /api/v1/sessions/{id} | 更新会话（标题/标签/评分） |
| DELETE | /api/v1/sessions/{id} | 软删除会话 |
| GET | /api/v1/sessions/{id}/messages | 获取会话消息列表 |
| GET | /api/v1/sessions/{id}/export | 导出会话（Markdown/JSON） |

### B.7 文档管理路由

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/v1/documents/upload | 上传文档 |
| GET | /api/v1/documents | 列出文档 |
| GET | /api/v1/documents/{id} | 获取文档详情 |
| GET | /api/v1/documents/{id}/preview | 预览文档 |
| DELETE | /api/v1/documents/{id} | 删除文档 |
| GET | /api/v1/documents/search | 搜索文档（文件名 FTS + 语义） |
| GET | /api/v1/documents/stats | 文档统计看板 |

### B.8 知识库路由

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/v1/knowledge/retrieve | 知识检索 |
| POST | /api/v1/knowledge/build | 构建知识图谱 |
| GET | /api/v1/knowledge/entities | 查询实体列表 |
| GET | /api/v1/knowledge/entities/{id} | 查询实体详情 |

### B.9 其他路由

| 方法 | 路径 | 功能 | 所属模块 |
|------|------|------|---------|
| POST | /api/v1/interact | 统一交互入口（意图分流） | interact |
| GET | /api/v1/tasks/{task_id} | 任务状态查询 | generate |
| GET | /api/v1/tasks/{task_id}/events | 任务事件流（SSE） | streaming |
| POST | /api/v1/web-index/url | 索引单 URL | web_indexing |
| POST | /api/v1/web-index/crawl | 启动爬虫 | web_indexing |
| POST | /api/v1/batch/trigger/{task_name} | 手动触发定时任务 | batch |
| GET | /api/v1/batch/schedule | 查看定时任务配置 | batch |

---


---

---

## 附篇 C：Alembic 数据库迁移历史

| 迁移 Revision | 文件名 | 内容 |
|--------------|--------|------|
| 938e6d4dcfd6 | init_all_tables.py | 初始化所有核心表：users, organizations, workspaces, roles, team_members, sessions, session_messages, llm_call_logs, budget_configs |
| a1b2c3d4e5f6 | add_block_e_tables.py | 新增Block E相关表：documents, web_resources, image_chunks, comments, suggestions, changelog |
| d4e5f6g7h8i9 | add_session_langgraph_fields.py | sessions表增加 thread_id, checkpoint_ts, current_node, interrupt_stage 字段以支持LangGraph checkpoint绑定 |

---


---

---

## 附篇 D：Docker Compose 服务拓扑

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: prd2tsd
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  neo4j:
    image: neo4j:5-enterprise
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/neo4jpassword

  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"

  celery_worker:
    build: .
    command: celery -A app.batch.tasks worker --loglevel=info
    depends_on: [redis, postgres]

  celery_beat:
    build: .
    command: celery -A app.batch.tasks beat --loglevel=info
    depends_on: [redis, postgres]

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"
      - "4317:4317"

  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]

volumes:
  pgdata:
```

---


---

---

## 附篇 E：代码质量与工程规范

### E.1 代码行数限制

```
每个函数 ≤ 50 行（超过必须拆）
每个文件 ≤ 300 行（超过必须拆）
每个类 ≤ 200 行（超过必须拆）
```

### E.2 技术栈合规

```bash
# 每次生成后检查违规依赖
grep -c "langchain" requirements.txt || echo "0"  # 必须输出 0

# 每次 Session 必须运行
pytest tests/test_tech_stack_compliance.py -v      # 必须全绿
pytest tests/test_lint.py -v                       # 注释完整性检查
```

### E.3 禁止模式清单

```python
# ❌ 绝对禁止
def foo():
    pass                       # pass 占位

raise NotImplementedError      # 未实现标记

# TODO: implement              # TODO 注释

# type: ignore[xxx]           # 除非有明确理由注释

from langchain import ...      # 黑名单库禁止
from langchain_community import ...
from langchain_openai import ...

from openai import OpenAI       # 禁止自己创建 LLM 客户端

# ✅ 允许
# VIBE_DEFER(块 C): 此处接入 Analysis Layer，当前返回 Mock 数据

from app.llm_gateway import gateway  # 通过 Gateway 统一使用 LLM
from app.llm_gateway.langchain_adapter import GatewayChatModel  # LangChain 适配器
```

### E.4 文件结构约定

```bash
# 每个模块的标准结构
app/<module>/
├── __init__.py       # 只导出公开 API
├── models.py         # Pydantic/SQLAlchemy 数据模型
├── service.py        # 核心业务逻辑
├── repository.py     # 数据访问层
└── nodes/            # 仅 Agent Layer 有此目录
    └── <node_name>.py
```

### E.5 docstring 规范

```python
# ✅ 合格的注释（Google 风格）
def retrieve(self, query: str, top_k: int = 10) -> list[str]:
    """检索相关知识上下文。

    Args:
        query: 查询文本。
        top_k: 返回结果数。

    Returns:
        相关文本片段列表。

    Raises:
        ConnectionError: 数据库连接失败时抛出。
    """
    ...

# ❌ 不合格
def retrieve(self, query: str, top_k: int = 10):
    return []
```

---


---

---

## 附篇 F：测试体系

### F.1 测试分层

| 层级 | 目录 | 运行命令 | 要求 |
|------|------|---------|------|
| 单元测试 | tests/unit/ | pytest tests/unit/ -v | 每个模块独立 |
| 集成测试 | tests/integration/ | pytest tests/integration/ -v | 模块间联通 |
| 端到端测试 | tests/e2e/ | pytest tests/e2e/ -v | 全链路 |
| 技术栈合规 | tests/test_tech_stack_compliance.py | pytest tests/test_tech_stack_compliance.py -v | 禁止黑名单库 |
| Lint 检查 | tests/test_lint.py | pytest tests/test_lint.py -v | 注释完整性 |

### F.2 关键测试用例

```python
# tests/e2e/test_full_flow.py
@pytest.mark.asyncio
async def test_full_pipeline():
    """端到端测试：完整PRD到TSD流水线。"""
    prd_raw = load_fixture("sample_prd.md")

    result = await run_pipeline(prd_raw)

    assert result.status == "complete"
    assert len(result.generation.content) > 100
    assert result.evaluation.overall_score > 0

# tests/unit/test_streaming.py - 16 个单元测试
# tests/unit/block_f/ - 46 个单元测试
```

### F.3 每个 Phase 结束时的端到端验证

```python
# tests/integration/test_pipeline.py
# 这个文件在 Phase 0 创建，每个 Phase 替换一部分 Mock

@pytest.mark.asyncio
async def test_full_pipeline():
    prd_raw = load_fixture("sample_prd.md")

    # Phase 0: 全是 Mock → 纯 LLM 链路
    # Phase 1: Mock 换为真实文件存储
    # Phase 2: Mock 换为真实向量检索
    # Phase 3: Mock 换为真实图检索
    # Phase 4: 所有 Mock 替换完毕，真实全链路
    # Phase 5: 在已有链路上增加新功能测试

    result = await run_pipeline(prd_raw)
    assert result.status == "complete"
    assert len(result.generation.content) > 100
```

---


---

---

## 附篇 G：常见问题排查指南

### G.1 任务创建后一直 running 不推进

```
1. 检查 PostgreSQL 是否正常运行:
   docker compose ps postgres

2. 检查 langgraph_checkpoints 表是否存在:
   SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'langgraph_checkpoints')

3. 检查 orchestrator 是否正确编译并注入到 TaskManager:
   日志中应该有 "主编排图编译完成" 的日志

4. 查看应用日志:
   docker compose logs app | grep -i error
```

### G.2 LLM 调用返回空响应

```
1. 检查 API Key 配置:
   echo $MODEL_CONFIG__LLM__DEEPSEEK__API_KEY

2. 检查 CircuitBreaker 状态:
   日志中搜索 "CircuitBreaker.*OPEN"

3. 查看 Failover 链:
   日志中搜索 "AllProvidersUnavailableError"

4. 检查护栏日志:
   日志中搜索 "guardrail.*blocked"
```

### G.3 SSE 连接断开

```
1. 检查 Nginx 配置:
   proxy_set_header X-Accel-Buffering no;

2. 检查 keepalive 超时设置:
   Nginx proxy_read_timeout 需 > 30s

3. 检查 EventBus queue:
   日志中搜索 "订阅者队列已满，丢弃事件"
```

### G.4 知识检索无结果

```
1. 检查 Neo4j 实体数量:
   MATCH (e:KGEntity) RETURN count(e)

2. 检查 PGVector 索引:
   SELECT count(*) FROM text_unit_embeddings

3. 检查 ReflectionJudge 日志:
   日志中搜索 "检索反思.*refine"

4. 手动触发知识图谱构建:
   POST /api/v1/knowledge/build
```

### G.5 会话续接后 LLM 不记得之前的讨论

```
1. 确认 session.thread_id 正确传递到 config:
   config = {"configurable": {"thread_id": session.thread_id}}

2. 确认 PostgresSaver 中该 thread_id 的 checkpoint 存在:
   SELECT * FROM langgraph_checkpoints WHERE thread_id = 'xxx-yyy-zzz'

3. 确认 MemoryRetriever 正确加载了历史消息:
   日志中应有 "记忆检索完成: retrieved=N memories"

4. 确认 ContextCompressor 没有过度压缩:
   检查 compressed_context 的长度和内容
```

---


---

---

## 附篇 H：项目演进时间线

| 日期 | 里程碑 | 关键变更 |
|------|--------|---------|
| 2026-07-24 | Gateway 加固 | 线程安全修复、统一定价常量模块、配置补全、Auth 安全增强 |
| 2026-07-26 | SSE 架构设计 | EventBus 设计、4个SSE端点、14种事件类型、Provider stream_complete 抽象 |
| 2026-07-27 | Block E 全面实施 | SSE 实现集成、会话历史完整CRUD、文档管理上传去重预览搜索、CSV/Web/多模态索引 |
| 2026-07-27 | Block F 全面实施 | 工具系统(ToolRegistry)、7个护栏插件、CircuitBreaker、Provider Failover、记忆增强、Prompt版本管理、Agent行为回放 |
| 2026-07-27 | 全链路深度审查 | 43节点+18路由模块逐文件审查、发现5个严重运行时问题+7个数据流断裂+3个架构缺陷+12处自定义流程替代LangGraph |
| 2026-07-27 | 架构重构方案 | deep-review-fix-plan.md、LangGraph全链路编排+LangChain接管节点内部、错误处理进入护栏体系 |
| 2026-07-28 | Phase 1-8 实施 | PostgreSQL Checkpointer、全链路编排(SSE/会话/记忆入图)、数据流修复(stakeholders/clarity_issues消费者)、死代码清理(3文件)、GatewayChatModel(LangChain适配器)、护栏扩展(3个新护栏)、知识层Protocol接口 |
| 2026-07-28 | Phase 2-5 收尾 | 意图路由接入(classify → route_by_intent)、SSE副作用移入ChatNode/KnowledgeQANode、TaskManager适配chat_response、GenerationAdapter export_formats双向传递、Session thread_id绑定、死代码清理(3个孤儿测试) |
| 2026-07-28 | LangChain 大规模重构 | 23个节点从手动call_llm_async()+手动JSON解析改为ChatPromptTemplate+GatewayChatModel+PydanticOutputParser、4个tools.py删除死代码、新增planning_layer/output_models.py(6个Pydantic输出模型) |
| 2026-07-28 | 全量 Bug 修复 | 7项critical修复：chat.py任务创建返回值错误、SaveSessionNode DB会话依赖修复、BatchScheduler.trigger_now空实现修复、image_encoder NotImplementedError降级、2处except Exception: pass改为logger.warning |

---


---

---

## 附篇 I：与业界方案深度对比

| 维度 | PRD2TSD Agents | LangChain AgentExecutor | AutoGPT | MetaGPT | CrewAI |
|------|---------------|------------------------|---------|---------|--------|
| **编排方式** | LangGraph 显式 StateGraph | 隐式 ReAct 循环 | 隐式循环 | 隐式角色扮演 | 隐式任务委派 |
| **可控性** | 100%（每个步骤显式定义） | 低（黑盒决策） | 低 | 中（SOP定义） | 中 |
| **Human-in-the-Loop** | ✅ 原生 interrupt/resume | ❌ 需自行实现 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **Checkpoint 持久化** | ✅ PostgreSQL | ⚠️ 可选 SQLite | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **崩溃恢复** | ✅ 从 checkpoint 续传 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **多租户隔离** | ✅ RBAC + ABAC | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **SSE 流式推送** | ✅ 14种事件类型 | ⚠️ 仅 LLM token 流 | ❌ 不支持 | ❌ 不支持 | ⚠️ 基础 |
| **护栏安全** | ✅ 7个可插拔护栏 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **熔断降级** | ✅ Circuit Breaker + Failover 链 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **知识检索** | ✅ Neo4j+PGVector 双路 + Reflection | ⚠️ 基础 RAG | ⚠️ 基础向量 | ⚠️ 基础 | ⚠️ 基础 |
| **迭代自评** | ✅ 10维评分 + 校准 + 自动回退 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **多模型路由** | ✅ Gateway 统一管理多Provider | ⚠️ 单一 Provider | ⚠️ 单一 | ⚠️ 单一 | ⚠️ 单一 |
| **文档导出** | ✅ Markdown/PDF/DOCX/HTML | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |
| **统一交互入口** | ✅ 对话/提问/文档分析/生成单一入口 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 |

---


---

---

## 附篇 J：面试常见追问及回答模板

### Q1: 为什么不用纯 LangChain 做 Agent？

```
LangChain 的 AgentExecutor 是一个黑盒的 ReAct 循环。你给它一个 prompt
和一组工具，它自己在内部循环"思考→行动→观察→思考..."直到完成。

问题在于：
1. 你无法精确控制每一步做什么——AgentExecutor 自己决定什么时候调工具、什么时候退出
2. 你无法在中间插入 Human-in-the-Loop——没有原生 interrupt/resume 机制
3. 你无法做崩溃恢复——AgentExecutor 没有 checkpoint 概念

我们的方案：
- 用 LangGraph StateGraph 替代 AgentExecutor——显式定义每个节点和每条边
- 每个节点就是一个 Python async 函数，你可以精确控制它的行为
- 用 interrupt() 和 Command(resume=...) 做人工审核
- 用 PostgresSaver 做崩溃恢复

但是我们没有完全放弃 LangChain——在节点内部，我们用
ChatPromptTemplate + GatewayChatModel + PydanticOutputParser
做结构化的 LLM 调用。LangGraph 负责"图怎么走"，LangChain 负责"节点内部 LLM 怎么调"。
```

### Q2: PostgresSaver vs MemorySaver 的区别和选择？

```
MemorySaver 是 LangGraph 的默认 checkpointer，纯内存实现。

优点：零配置，测试方便
缺点：重启全丢，不适合生产

PostgresSaver 把每一步的 checkpoint 写入 PostgreSQL 的
langgraph_checkpoints 表。

优点：
1. 崩溃恢复：服务挂了重启，用相同 thread_id 继续跑，LangGraph 自动从
   最近的 checkpoint 恢复，重放已完成的节点，继续未完成的
2. 多线程安全：多个请求可以并发操作不同 thread
3. Time-Travel 调试：可以 get_state 查看历史状态，update_state 修改历史状态
4. 与 sessions 表的 thread_id 字段绑定：会话续接时自动恢复 Graph 状态

代价：
- 每次 checkpoint 有一次 PG 写入（但 LangGraph 已优化为批量写入，非每 token 写入）
- 需要 PostgreSQL 运行
```

### Q3: Adapter 模式为什么重要？为什么不让 Layer 直接操作 OrchestratorState？

```
核心原因：保持 Layer 的独立性，使其可以独立编译和独立测试。

如果 Planning Node 直接 import OrchestratorState：
- Planning Layer 的单元测试就需要构造完整的 OrchestratorState
- 改 OrchestratorState 的结构会影响所有 Layer
- Layer 之间形成隐式耦合

使用 Adapter 模式：
- 每个 Layer 只知道自己 State 的结构（PlanningState）
- Adapter 负责 OrchestratorState ↔ PlanningState 的映射
- 测试 Planning Layer 时只需要构造 PlanningState
- 换一个 Planning 实现，只需换 Adapter 的 graph 引用
- 符合"依赖倒置原则"——Layer 依赖自己的 State，不依赖 OrchestratorState
```

### Q4: 护栏系统为什么放在 Gateway 层而不是放在每个 LangGraph 节点里？

```
护栏是 LLM 调用的安全机制，不是某个节点的业务逻辑。

放在 Gateway 层的好处：
1. 统一性：无论哪个节点调 LLM（Analysis 的 requirement_extractor 还是
   Generation 的 section_writer），都经过同一套护栏
2. pre_llm / post_llm 两阶段的执行顺序由 Gateway 统一管理
   执行顺序: PromptInjection → PII → Timeout → [LLM Call] → ContentSafety → OutputValidator → EmptyResponse → RetryDecision
3. 新增护栏不需要改图结构——在 Gateway 初始化时 register 即可
4. 护栏结果与 LangGraph 路由的联动：
   错误类护栏（Timeout/EmptyResponse/RetryDecision）的 GuardrailResult.metadata
   会传递给 LangGraph 条件路由，实现"护栏结果驱动图路由"
   例如: EmptyResponse → metadata.retry=True → LangGraph route 到 retry 节点
```

### Q5: 如果有 100 个并发任务，系统怎么处理？

```
1. 任务创建层：
   TaskManager.create_task() 立即返回 task_id，用 asyncio.create_task()
   创建后台协程，不阻塞 HTTP 响应

2. 数据库连接池：
   PostgreSQL pool_size=10 + max_overflow=20 = 最多 30 个并发连接
   连接在 asyncpg 层面自动管理，await 等待可用连接

3. LLM 调用限流：
   RateLimiter 按 workspace 维度限制 RPM（每分钟请求数）和 TPM（每分钟 token 数）
   超限请求排队等待或返回 429

4. 熔断保护：
   如果某个 Provider 连续失败 3 次，CircuitBreaker 进入 OPEN 状态
   后续请求直接失败（不再继续打挂掉的 Provider），30 秒后半开试探恢复

5. Failover 链：
   Primary Provider 不可用 → 自动切换到 Fallback
   如果所有 Provider 都不可用 → AllProvidersUnavailableError → 任务标记失败

6. 预算控制：
   如果 workspace 月预算超过 90%，自动降级到低成本模型（deepseek-chat → gpt-4o-mini）

7. 定时任务解耦：
   知识图谱刷新、会话清理等定时任务通过 Celery Worker 独立进程执行
   不影响主 API 服务的响应时间
```

### Q6: 知识检索的反思机制是怎么工作的？

```
ReflectionJudge 是知识检索层的自我纠偏机制。

工作流程：
1. 正常检索：IntentRouter → QueryRewriter → LocalSearch/GlobalSearch → RRFFusion
2. 反思判断：将检索结果和原始查询一起发给 LLM
   Prompt: "这些检索结果满足用户需求吗？如果不满足，缺少什么？给出修正后的搜索查询。"
3. LLM 返回 judgment:
   - accept: 结果满足需求 → 继续后续流程
   - refine: 结果不满足 → 返回 refined_query（修正后的搜索查询）
4. 如果 refine: 用 refined_query 重新检索，再次反思
5. 最多 3 轮反思

示例：
原始查询: "用户服务用什么技术栈？"
检索结果: [关于订单服务的文档...]
反思判断: refine
  - reason: "缺少用户服务相关的技术栈信息"
  - refined_query: "用户微服务 技术栈 数据库 框架"

第二轮检索: "用户微服务 技术栈 数据库 框架"
检索结果: [Spring Boot + PostgreSQL + Redis...]
反思判断: accept → 继续

这解决了传统 RAG 的痛点：第一次检索不准就没办法了。
```

### Q7: LangGraph 的 interrupt/resume 机制是怎么实现的？

```
LangGraph 的 interrupt() 是一个特殊的 Python 调用，它会：
1. 暂停当前节点的执行
2. 将当前 State 写入 Checkpointer（PostgresSaver）
3. 抛出 GraphInterrupt 异常（LangGraph 内部处理，对调用方透明）
4. 调用方（TaskManager）检测到 astream 循环结束但 status 仍为 "running"
   → 标记任务为 "paused"

恢复时：
1. 调用方用相同的 thread_id 重新 astream
2. 传入 Command(resume=resume_value)
3. LangGraph 从 Checkpointer 加载最近的 checkpoint
4. 重放已完成的节点（自动跳过）
5. 在 interrupt() 处恢复执行，interrupt() 的返回值就是 resume_value
6. 继续执行后续节点

关键的线程安全保证：
- thread_id 是 LangGraph checkpoint 的唯一标识
- 同一个 thread_id 的多次 astream 调用自动排队
- PostgresSaver 使用 PostgreSQL 的行锁保证并发安全

为什么用 Command(resume=value) 而不是直接传参？
- 如果直接把 resume_value 作为新的 state 输入，LangGraph 会把它当作
  新的初始状态来执行（重新跑所有节点），而不是从中断点恢复
- Command(resume=value) 告诉 LangGraph："我不是新的输入，
  我是给上一个被 interrupt() 暂停的节点的返回值"
```

### Q8: 这个项目最大的技术挑战是什么？

```
最大的技术挑战是如何在保持 LangGraph 的编排灵活性、LangChain 的节点内便利性
和自研 LLM Gateway 的生产级能力的"不可能三角"中找到平衡。

具体来说：
1. LangGraph 擅长编排，但它的节点只能接收/返回 State，不提供 LLM 调用能力
2. LangChain 擅长 Prompt 管理和结构化输出，但它的 ChatOpenAI 没有成本追踪、
   限流、缓存、护栏等能力
3. 自研 LLM Gateway 有完整的生产级能力，但它不是 LangChain 的 BaseChatModel，
   无法直接用于 ChatPromptTemplate | llm | PydanticOutputParser 的 LCEL 链

解决方案：GatewayChatModel
- 实现 LangChain 的 BaseChatModel 接口（_agenerate / _astream / bind_tools）
- 内部委托给自研 LLM Gateway 的 complete() / stream_complete()
- 这样 Agent 节点内部可以用 LangChain 的全部能力（PromptTemplate / OutputParser）
- 同时保留 Gateway 的全部生产级能力（限流/缓存/熔断/护栏/成本追踪）
- 而且不引入被 tech-stack.yml 禁止的 langchain-openai 包
```

---

> **文档结束** — 完整架构、全部模块、运行时链路、API清单、数据模型、
> Docker拓扑、代码规范、测试体系、故障排查、演进时间线、业界对比和面试问答。
> 总计约 5000 行，覆盖 PRD2TSD Agents 项目的全部关键知识点。
> 保存为 `docs/full-architecture-deep-dive.md`。


---

---

## 附篇 K：完整 Contracts 数据模型

```python
# === 知识检索模型 ===
@dataclass
class ScoredDoc:
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class RetrievalContext:
    query: str
    docs: list[ScoredDoc]
    search_mode: str  # local / global / hybrid

# === 分析层基础模型 ===
@dataclass
class Requirement:
    id: str
    title: str
    description: str
    priority: str = "medium"
    category: str = "functional"

@dataclass
class Constraint:
    id: str
    description: str
    type: str = "technical"

@dataclass
class AnalysisResult:
    project_name: str
    summary: str
    requirements: list[Requirement]
    constraints: list[Constraint]
    metadata: dict[str, Any] = field(default_factory=dict)

# === 规划层基础模型 ===
@dataclass
class TechChoice:
    component: str
    technology: str
    version: str = ""
    reason: str = ""

@dataclass
class Component:
    name: str
    description: str
    tech_stack: list[TechChoice] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

# === Pydantic 增强模型 (Block C 新增) ===
class RequirementDetail(BaseModel):
    id: str
    type: Literal["functional", "non_functional"]
    category: str
    priority: Literal["P0", "P1", "P2", "P3"]
    description: str
    actor: str
    acceptance_criteria: list[str] = []
    source_section: str = ""

class ConstraintDetail(BaseModel):
    type: Literal["technical", "performance", "time", "budget", "compliance", "team"]
    description: str
    severity: Literal["must", "should", "could"]
    source_section: str = ""

class AnalysisResultDetail(BaseModel):
    project_name: str
    summary: str
    domain_tags: list[str] = []
    requirements: list[RequirementDetail] = []
    constraints: list[ConstraintDetail] = []
    dependency_graph: Any = None
    quality_scores: dict[str, float] = {}
    effort_estimate: dict[str, Any] = {}
    stakeholders: list[dict[str, Any]] = []
    clarity_issues: list[dict[str, Any]] = []

class PatternEval(BaseModel):
    name: str
    score: float
    pros: list[str] = []
    cons: list[str] = []
    fit_explanation: str = ""

class PlanningResultDetail(BaseModel):
    architecture_patterns: list[PatternEval] = []
    tech_stack: list[Any] = []
    components: list[Any] = []
    data_architecture: dict[str, Any] = {}
    api_plan: dict[str, Any] = {}
    deployment_plan: dict[str, Any] = {}
    cost_estimates: list[dict[str, Any]] = []
    timeline: dict[str, Any] = {}
    skill_gaps: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}

class SectionOutline(BaseModel):
    number: int
    title: str
    subsections: list[str] = []
    estimated_tokens: int = 0

class GenerationResultDetail(BaseModel):
    title: str = ""
    sections: list[dict[str, Any]] = []
    outline: list[SectionOutline] = []
    diagrams: list[str] = []
    code_scaffold: dict[str, str] = {}
    export_formats: dict[str, str] = {}
    summary: str = ""
    total_tokens: int = 0

class EvaluationReportDetail(BaseModel):
    overall_score: float = 0.0
    dimension_scores: dict[str, float] = {}
    critical_issues: list[dict[str, Any]] = []
    recommendations: list[str] = []
    conclusion: str = ""
    p0_coverage: float = 0.0
    calibrations_applied: list[str] = []
```

---


---

---

## 附篇 L：每层 4 个 Agent 节点的完整代码模式

### K.1 Analysis Layer 节点代码模板

所有 Analysis Layer 节点使用统一的代码模式：

```python
# app/analysis_layer/nodes/requirement_extractor.py

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.analysis_layer.models import AnalysisState
from app.llm_gateway.langchain_adapter import GatewayChatModel


# 步骤 1: 定义输出模型
class RequirementItem(BaseModel):
    id: str = Field(description="需求编号，格式 FR-xxx 或 NFR-xxx")
    type: str = Field(description="functional 或 non_functional")
    category: str = Field(description="需求所属类别")
    priority: str = Field(description="P0/P1/P2/P3")
    description: str = Field(description="需求描述")
    actor: str = Field(description="需求方角色")
    acceptance_criteria: list[str] = Field(default_factory=list)

class RequirementList(BaseModel):
    requirements: list[RequirementItem]


# 步骤 2: 定义 System Prompt
SYSTEM_PROMPT = """你是一个资深的需求分析师。请从以下PRD中提取所有需求。

要求：
1. 功能需求以 FR-xxx 编号，非功能需求以 NFR-xxx 编号
2. 每个需求包含：类型、类别、优先级、描述、需求方角色、验收标准
3. 优先级判断标准：
   - P0: 核心功能，无此功能系统无法运行
   - P1: 重要功能，对用户体验有重大影响
   - P2: 一般功能，可延期实现
   - P3: 锦上添花，可在后续版本中实现
"""


# 步骤 3: 定义节点类
class RequirementExtractorNode:
    """需求提取节点 — 从 PRD 中提取所有功能和非功能需求。

    使用 LangChain 的 ChatPromptTemplate + GatewayChatModel + PydanticOutputParser
    做结构化的 LLM 调用，替代原来的手动 call_llm_async() + json.loads()。
    """

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        """初始化需求提取节点。

        Args:
            llm: GatewayChatModel 实例（可选，未提供则自动创建）。
        """
        self.llm = llm or GatewayChatModel(
            task_type="analysis.requirement",
            layer="analysis",
            node="requirement_extractor",
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "PRD内容：\n{prd_text}"),
        ])

        self.parser = PydanticOutputParser(pydantic_object=RequirementList)

        # LCEL 链: prompt | llm | parser
        self.chain = self.prompt | self.llm | self.parser

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行需求提取。

        Args:
            state: 当前 AnalysisState。

        Returns:
            更新了 extracted_requirements 的 AnalysisState。
        """
        prd_text = state.get("prd_raw", "")

        if not prd_text.strip():
            state["extracted_requirements"] = []
            return state

        # 一次调用完成: Prompt 构建 → LLM 调用 → JSON 解析 → Pydantic 验证
        result: RequirementList = await self.chain.ainvoke({
            "prd_text": prd_text[:8000],  # 截断过长输入
        })

        # 转换为 RequirementDetail
        from contracts.interfaces import RequirementDetail
        requirements = [
            RequirementDetail(
                id=r.id, type=r.type, category=r.category,
                priority=r.priority, description=r.description,
                actor=r.actor, acceptance_criteria=r.acceptance_criteria,
            )
            for r in result.requirements
        ]

        state["extracted_requirements"] = requirements
        return state
```

### K.2 Planning Layer 节点代码模板

```python
# app/planning_layer/nodes/pattern_recommend.py

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.planning_layer.models import PlanningState
from app.llm_gateway.langchain_adapter import GatewayChatModel


class PatternCandidate(BaseModel):
    name: str = Field(description="架构模式名称")
    score: float = Field(description="适合度评分 0-10")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    fit_explanation: str = Field(description="为什么适合/不适合这个项目")

class PatternRecommendation(BaseModel):
    patterns: list[PatternCandidate]


SYSTEM_PROMPT = """你是一个资深架构师。根据需求分析结果，推荐2-3个候选架构模式。

常见架构模式：
- 微服务 (Microservices)
- 事件驱动 (Event-Driven)
- CQRS + Event Sourcing
- 分层架构 (Layered)
- 六边形架构 (Hexagonal/Ports & Adapters)
- 服务化架构 (SOA)
- Serverless

对每个候选模式给出：适合度评分(0-10)、优缺点、为什么适合/不适合。
"""


class PatternRecommendNode:
    """架构模式推荐节点 — 根据需求分析推荐架构模式候选。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        self.llm = llm or GatewayChatModel(
            task_type="planning.pattern",
            layer="planning",
            node="pattern_recommend",
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "需求分析结果：\n{analysis_json}"),
        ])

        self.parser = PydanticOutputParser(pydantic_object=PatternRecommendation)
        self.chain = self.prompt | self.llm | self.parser

    async def run(self, state: PlanningState) -> PlanningState:
        analysis_result = state.get("analysis_result")
        if analysis_result is None:
            return state

        import json
        analysis_json = json.dumps(analysis_result, default=str, ensure_ascii=False)

        result: PatternRecommendation = await self.chain.ainvoke({
            "analysis_json": analysis_json[:6000],
        })

        from contracts.interfaces import PatternEval
        state["architecture_patterns"] = [
            PatternEval(
                name=p.name, score=p.score,
                pros=p.pros, cons=p.cons,
                fit_explanation=p.fit_explanation,
            )
            for p in result.patterns
        ]
        return state
```

### K.3 Generation Layer 节点代码模板

```python
# app/generation_layer/nodes/section_writer.py

from app.generation_layer.models import GenerationState
from app.llm_gateway.langchain_adapter import GatewayChatModel
from app.streaming.models import SseEvent


class SectionWriterNode:
    """章节撰写节点 — 逐节流式生成技术方案文档。

    使用 GatewayChatModel.stream_complete() 流式调用 LLM，
    每 200 字符通过 EventBus 推送 generation.chunk SSE 事件。
    """

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        self.llm = llm or GatewayChatModel(
            task_type="generation.section_writer",
            layer="generation",
            node="section_writer",
        )

    async def run(self, state: GenerationState) -> GenerationState:
        task_id = state.get("task_id", "")
        outline = state.get("outline", [])
        planning_result = state.get("planning_result")
        section_contents = state.get("section_contents", {})

        # 获取 EventBus
        event_bus = None
        runtime = state.get("_runtime")
        if runtime:
            event_bus = getattr(runtime, "event_bus", None)

        for section in outline:
            section_name = section.get("title", "")

            # 构造 Prompt
            prompt = self._build_section_prompt(section, planning_result, section_contents)

            # 流式调用 LLM
            full_text = ""
            async for token in self.llm.astream(prompt):
                full_text += token

                # 每 200 字符推送一次 SSE
                if event_bus and len(full_text) % 200 < len(token) + 1:
                    await event_bus.publish(
                        f"task:{task_id}",
                        SseEvent(
                            type="generation.chunk",
                            payload={
                                "content": token,
                                "section": section_name,
                            },
                        ),
                    )

            section_contents[section_name] = full_text

            # 章节完成通知
            if event_bus:
                await event_bus.publish(
                    f"task:{task_id}",
                    SseEvent(
                        type="generation.section",
                        payload={
                            "section": section_name,
                            "status": "done",
                            "content_length": len(full_text),
                        },
                    ),
                )

        state["section_contents"] = section_contents
        return state
```

### K.4 Evaluation Layer 节点代码模板

```python
# app/evaluation/nodes/coverage_checker.py

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.evaluation.models import EvaluationState
from app.llm_gateway.langchain_adapter import GatewayChatModel


class CoverageResult(BaseModel):
    score: float = Field(description="覆盖率评分 0-10")
    covered_requirements: list[str] = Field(default_factory=list)
    uncovered_requirements: list[str] = Field(default_factory=list)
    p0_coverage: float = Field(description="P0需求覆盖率")
    comments: str = ""


SYSTEM_PROMPT = """你是一个技术方案评审专家。请检查生成的技术方案是否覆盖了PRD中的所有需求。

评分标准：
- 10分: 所有需求都有对应的设计方案，P0需求100%覆盖
- 8分: 大部分需求有对应方案，少量P2/P3遗漏
- 6分: 部分需求遗漏，但不影响核心功能
- 4分: 关键需求遗漏
- 2分: 大部分需求未覆盖

返回JSON格式。
"""


class CoverageCheckerNode:
    """需求覆盖率检查节点 — 检查方案是否覆盖所有PRD需求。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        self.llm = llm or GatewayChatModel(
            task_type="evaluation.scoring",
            layer="evaluation",
            node="coverage_checker",
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "PRD需求：\n{requirements}\n\n生成的方案：\n{generation}"),
        ])

        self.parser = PydanticOutputParser(pydantic_object=CoverageResult)
        self.chain = self.prompt | self.llm | self.parser

    async def run(self, state: EvaluationState) -> EvaluationState:
        requirements = state.get("analysis_result", {})
        generation = state.get("generation_result", {})

        import json
        result: CoverageResult = await self.chain.ainvoke({
            "requirements": json.dumps(requirements, default=str)[:4000],
            "generation": json.dumps(generation, default=str)[:4000],
        })

        dim_scores = state.get("dimension_scores", {})
        dim_scores["prd_coverage"] = result.score
        state["dimension_scores"] = dim_scores

        return state
```

---


---

---

## 附篇 M：完整配置示例文件

### L.1 .env 配置示例

```bash
# ===== Application =====
APP_NAME=prd2tsd
DEBUG=false
SECRET_KEY=change-me-to-a-random-secret-key-at-least-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ===== PostgreSQL =====
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/prd2tsd
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# ===== Redis =====
REDIS_URL=redis://localhost:6379/0
REDIS_POOL_SIZE=10

# ===== MinIO =====
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=prd2tsd
MINIO_SECURE=false

# ===== Neo4j =====
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4jpassword
NEO4J_DATABASE=neo4j

# ===== LLM: DeepSeek =====
MODEL_CONFIG__LLM__DEEPSEEK__API_KEY=sk-your-deepseek-api-key
MODEL_CONFIG__LLM__DEEPSEEK__BASE_URL=https://api.deepseek.com/v1
MODEL_CONFIG__LLM__DEEPSEEK__DEFAULT_MODEL=deepseek-chat

# ===== LLM: OpenAI (Fallback) =====
MODEL_CONFIG__LLM__OPENAI__API_KEY=sk-your-openai-api-key
MODEL_CONFIG__LLM__OPENAI__BASE_URL=https://api.openai.com/v1
MODEL_CONFIG__LLM__OPENAI__DEFAULT_MODEL=gpt-4o-mini

# ===== Embedding =====
MODEL_CONFIG__EMBEDDING__OPENAI__API_KEY=sk-your-openai-api-key
MODEL_CONFIG__EMBEDDING__OPENAI__BASE_URL=https://api.openai.com/v1
MODEL_CONFIG__EMBEDDING__OPENAI__DEFAULT_MODEL=text-embedding-3-small

# ===== Rerank =====
MODEL_CONFIG__RERANK__COHERE__API_KEY=your-cohere-api-key
MODEL_CONFIG__RERANK__COHERE__BASE_URL=https://api.cohere.com/v1
MODEL_CONFIG__RERANK__COHERE__DEFAULT_MODEL=rerank-english-v3.0

# ===== Judge (评测) =====
MODEL_CONFIG__JUDGE__OPENAI__API_KEY=sk-your-openai-api-key
MODEL_CONFIG__JUDGE__OPENAI__BASE_URL=https://api.openai.com/v1
MODEL_CONFIG__JUDGE__OPENAI__DEFAULT_MODEL=gpt-4o-mini

# ===== OpenTelemetry =====
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=prd2tsd

# ===== LangFuse =====
LANGFUSE_PUBLIC_KEY=pk-your-public-key
LANGFUSE_SECRET_KEY=sk-your-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com
```

### L.2 pyproject.toml 配置示例

```toml
[project]
name = "prd2tsd-agents"
version = "0.1.0"
description = "PRD to Tech Spec Documents — Multi-Agent Pipeline"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"
```

### L.3 prometheus.yml 配置示例

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prd2tsd'
    static_configs:
      - targets: ['app:8000']
    metrics_path: '/metrics'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

---


---

---

## 附篇 N：开发铁律回顾

### M.1 铁律零：技术栈锁定

```bash
# 编排层使用 LangGraph，Agent 节点内部使用 LangChain Core。
# RAG 框架：自实现（实体增强双路检索 + ReflectionJudge）。

# 每次生成后第一件事：检查有没有引入违规依赖
grep -c "langchain" requirements.txt || echo "0"
# 输出必须为 0
```

### M.2 铁律一：每次 Session 只做一个块

```
块 A → 块 B → 块 C → 块 D → 块 E → 块 F → 块 G
各块定义见 docs/phase-prompts.md。
不允许跳块。块 N 必须在块 N-1 的代码基础上做，且块 N-1 的集成测试必须全绿。
```

### M.3 铁律二：外部依赖一个一个加

```bash
# 1. 先 docker compose up 新服务
docker compose up -d <新服务>

# 2. 写一个独立的连接测试脚本
python -c "import psycopg2; conn = psycopg2.connect(...); print('连接成功')"

# 3. 这个脚本跑通后，再写业务代码
# 4. 业务代码写完后，运行集成测试
pytest tests/integration/test_pipeline.py -v
```

### M.4 铁律三：Contracts 不可变

```
contracts/ 目录下的所有文件在 Phase 0 定义后不允许修改。

如果发现必须改：
1. 在当前 Phase 文档中注明"需修改 Contracts"
2. 一次性改完 contracts/ 所有受影响的文件
3. 运行 pytest tests/test_contracts.py 确保所有模型可序列化
4. 通知所有使用该 contract 的 session 同步更新
```

### M.5 铁律四：每个 Phase 结束时必须有通过的端到端测试

```bash
pytest tests/ -v
# 必须全部通过，不能有 skipped / xfailed
```

### M.6 铁律五：不存在"下一阶段再修"的 TODO

```
❌ # TODO: 后面接真实数据库
❌ # FIXME: 这里需要错误处理
❌ raise NotImplementedError

在这个 Phase 内必须处理完。
如果某个功能确实不属于当前 Phase，就不要写它的桩代码。
```

### M.7 铁律六：改接口先改测试

```
1. 改 contracts/interfaces.py
2. 改 tests/ 中对应的 Mock
3. 运行测试（此时应该红）
4. 改实现代码
5. 运行测试（此时应该绿）

不允许先改实现再回来改测试。
```

### M.8 铁律七：技术栈由测试强制

```bash
pytest tests/test_tech_stack_compliance.py -v
# 如果导入了黑名单库（如 langchain），测试红 → 不允许合并
```

### M.9 铁律八：质量门禁从 Phase 0 第一天就启用

```
prd2tsd-agents/
├── pyproject.toml               # ruff + mypy + pytest 配置
├── .github/workflows/ci.yml     # PR 自动跑 lint + type-check + test
└── tests/
    ├── conftest.py
    ├── test_tech_stack_compliance.py  # 技术栈合规
    ├── test_lint.py                   # 注释完整性 + ruff 零错误
    └── test_e2e.py                    # 端到端测试
```

---


---

---

## 附篇 O：Block G 未实现计划（未来方向）

### N.1 Send() 并行扇出详细实现计划

```python
# 当前 Evaluation 9 个节点串行，总耗时 = sum(单节点延迟)
# 改造后：9 个节点并行，总耗时 = max(单节点延迟)

from langgraph.constants import Send

# Step 1: 定义 Fan-Out 节点
class FanOutEvalNode:
    def run(self, state: EvaluationState) -> list[Send]:
        """生成 9 个并行 Send。"""
        return [
            Send("coverage", state),
            Send("consistency", state),
            Send("feasibility", state),
            Send("architecture_quality", state),
            Send("security", state),
            Send("cost_eval", state),
            Send("implementability", state),
            Send("tech_advancement", state),
            Send("legal", state),
        ]

# Step 2: 修改图结构
graph.add_node("fan_out_eval", FanOutEvalNode().run)
graph.add_conditional_edges(
    "fan_out_eval",
    lambda s: [Send(...) for ...],  # 或用上面的 FanOutEvalNode
    {
        "coverage": "coverage",
        "consistency": "consistency",
        # ... 共 9 个映射
    },
)

# Step 3: 9 个节点并行执行后自动 Fan-In 到 scoring
for node in EVALUATOR_NODES:
    graph.add_edge(node, "scoring")

# 预期效果：
# - 耗时从 ~18s (9 × 2s) 降到 ~2s (max(单节点))
# - 9 个 LLM 调用并行发出，总 cost 不变
```

### N.2 原生 Subgraph 改造计划

```python
# 当前：手工 Adapter 调用子图
class AnalysisAdapter:
    async def run(self, state):
        result = await self.graph.ainvoke(input)  # 手工调用

# 改造后：LangGraph 原生子图
orchestrator_graph.add_node(
    "analysis",
    analysis_graph.compile(),  # 直接传入编译后的子图
)

# 优势：
# 1. LangGraph 自动管理子图生命周期
# 2. 子图内部的 checkpoint 与主图 checkpoint 合并
# 3. interrupt 可穿透子图（子图内部的 interrupt 会暂停主图）
# 4. 主图的 astream 可以看到子图内部的进度
```

### N.3 Multi-Agent Supervisor 模式

```python
# Supervisor Agent 协调多个 Worker Agent

class SupervisorAgent:
    """监督者 Agent — 协调多个 Worker Agent 并行工作。

    工作流程：
    1. 接收任务 → 分解为子任务
    2. 分配给 Analysis / Planning / Generation / Evaluation 四个 Worker
    3. 收集 Worker 的输出 → 综合决策
    4. 如果某个 Worker 输出质量不够 → 要求重新执行
    """

# 图结构：
# supervisor → [analysis_worker, planning_worker, generation_worker, evaluation_worker]
# 四个 worker 并行执行 → 结果汇总到 supervisor
# supervisor 判断 → 通过 / 需要修改某部分
```

---

> **附录结束** — 总计覆盖：节点代码模板、配置示例、开发铁律、未来方向。
> 与主文档合并后总行数约 5000 行。


---

---

## 附篇 P：项目目录完整结构

```
prd2tsd-agents/
├── .github/
│   ├── copilot-instructions.md          # Copilot 指令（Skill 加载要求 + 文档约束 + 铁的纪律）
│   ├── skills/
│   │   ├── ai-coding-rules/SKILL.md     # 唯一编码入口 skill（16 rules + debug-tools）
│   │   ├── grill-me/SKILL.md            # Socratic interrogator skill
│   │   ├── git/SKILL.md                 # Git 操作 skill
│   │   ├── code-review/SKILL.md         # 代码审查 skill
│   │   └── simplify/SKILL.md            # 代码简化 skill
│   └── workflows/
│       ├── ci.yml                       # PR 自动 lint + type-check + test
│       ├── deploy-prod.yml              # 手动触发生产部署
│       └── backup.yml                   # 定时备份
├── alembic/
│   ├── env.py                           # Alembic 环境配置
│   ├── script.py.mako                   # 迁移脚本模板
│   └── versions/
│       ├── 938e6d4dcfd6_init_all_tables.py
│       ├── a1b2c3d4e5f6_add_block_e_tables.py
│       └── d4e5f6g7h8i9_add_session_langgraph_fields.py
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI 入口 + lifespan
│   ├── task_manager.py                  # 异步任务管理器
│   ├── agents/                          # Block F: 工具系统
│   │   ├── __init__.py
│   │   ├── base.py                      # BaseTool 抽象基类
│   │   ├── context.py                   # ToolContext 数据类
│   │   ├── registry.py                  # ToolRegistry 全局注册器
│   │   ├── result.py                    # ToolResult 数据类
│   │   └── tools/                       # 具体工具实现
│   ├── analysis_layer/                  # C1: 需求分析层
│   │   ├── agent_graph.py               # Analysis StateGraph 构建
│   │   ├── models.py                    # AnalysisState TypedDict
│   │   ├── tools.py                     # 层内辅助函数
│   │   └── nodes/                       # 11 个分析节点
│   │       ├── document_parser.py
│   │       ├── lang_detector.py
│   │       ├── requirement_extractor.py
│   │       ├── constraint_analyzer.py
│   │       ├── dependency_analyzer.py
│   │       ├── domain_classifier.py
│   │       ├── quality_scorer.py
│   │       ├── effort_estimator.py
│   │       ├── stakeholder_analyzer.py
│   │       ├── clarity_checker.py
│   │       └── result_assembler.py
│   ├── planning_layer/                  # C2: 架构规划层
│   │   ├── agent_graph.py               # Planning StateGraph 构建
│   │   ├── models.py                    # PlanningState TypedDict
│   │   ├── output_models.py             # 6 个 Pydantic 输出模型
│   │   ├── tools.py                     # 层内辅助函数
│   │   └── nodes/                       # 12 个规划节点
│   │       ├── knowledge_augment.py
│   │       ├── pattern_recommend.py
│   │       ├── tech_stack_selection.py
│   │       ├── component_decomposition.py
│   │       ├── data_architecture.py
│   │       ├── api_planning.py
│   │       ├── deployment_planning.py
│   │       ├── cost_estimation.py
│   │       ├── timeline_planning.py
│   │       ├── skill_gap.py
│   │       ├── risk_quantification.py
│   │       ├── plan_self_check.py
│   │       └── plan_assembler.py
│   ├── generation_layer/                # C3: 方案生成层
│   │   ├── agent_graph.py               # Generation StateGraph 构建
│   │   ├── models.py                    # GenerationState TypedDict
│   │   ├── tools.py                     # 层内辅助函数
│   │   └── nodes/                       # 8 个生成节点
│   │       ├── outline_generator.py
│   │       ├── template_selector.py
│   │       ├── section_writer.py
│   │       ├── mermaid_diagram.py
│   │       ├── code_scaffold.py
│   │       ├── consistency_checker.py
│   │       ├── revision.py
│   │       ├── multi_format_export.py
│   │       └── document_assembler.py
│   ├── evaluation/                      # C4: 质量评测层
│   │   ├── agent_graph.py               # Evaluation StateGraph 构建
│   │   ├── models.py                    # EvaluationState TypedDict
│   │   ├── scoring.py                   # ScoringNode
│   │   ├── score_calibrator.py          # ScoreCalibrator
│   │   ├── tools.py                     # 层内辅助函数
│   │   └── nodes/                       # 9 个评测节点
│   │       ├── coverage_checker.py
│   │       ├── consistency_checker.py
│   │       ├── feasibility_evaluator.py
│   │       ├── architecture_quality.py
│   │       ├── security_compliance.py
│   │       ├── cost_evaluator.py
│   │       ├── implementability.py
│   │       ├── tech_advancement.py
│   │       └── legal_compliance.py
│   ├── orchestrator/                    # Block D: 主编排
│   │   ├── __init__.py                  # 公开导出
│   │   ├── main_graph.py                # build_orchestrator_graph + 节点定义
│   │   ├── state.py                     # OrchestratorState/Config/Runtime
│   │   ├── routing.py                   # needs_review 条件路由
│   │   ├── human_review.py              # HumanReviewNode (interrupt/resume)
│   │   ├── iteration.py                 # IterationDecider 迭代决策
│   │   ├── intent_classifier.py         # IntentClassifier 意图分类
│   │   ├── adapters/                    # 4 个 Adapter
│   │   │   ├── analysis_adapter.py
│   │   │   ├── planning_adapter.py
│   │   │   ├── generation_adapter.py
│   │   │   └── evaluation_adapter.py
│   │   └── nodes/                       # 图节点
│   │       ├── chat_node.py             # 纯对话节点
│   │       ├── retrieve_node.py         # 知识查询节点
│   │       ├── clarify_node.py          # 澄清节点
│   │       ├── intent_classify.py       # 意图分类节点
│   │       ├── retrieve_memory.py       # 记忆检索节点
│   │       ├── compress_memory.py       # 记忆压缩节点
│   │       └── save_session.py          # 会话保存节点
│   ├── knowledge_layer/                 # Block B: 知识层
│   │   ├── pipeline.py                  # RetrievalPipeline 主入口
│   │   ├── models.py                    # KGEntity, ScoredDoc, etc
│   │   ├── config.py                    # Neo4j/PGVector/LLM 配置
│   │   ├── graph_store.py               # Neo4j 封装
│   │   ├── vector_store.py              # PGVector 封装
│   │   ├── interfaces.py                # Protocol 接口定义
│   │   ├── ingestion/                   # 文档摄取
│   │   └── retrieval/                   # 检索引擎
│   ├── llm_gateway/                     # Block A: LLM Gateway
│   │   ├── __init__.py                  # LLMGateway 门面类
│   │   ├── models.py                    # Pydantic 模型
│   │   ├── config_manager.py            # 模型配置管理器
│   │   ├── cost_tracker.py              # 成本追踪
│   │   ├── cache.py                     # 语义缓存
│   │   ├── rate_limiter.py              # 速率限制
│   │   ├── budget_controller.py         # 预算控制
│   │   ├── failover.py                  # Provider Failover
│   │   ├── langchain_adapter.py         # GatewayChatModel
│   │   ├── providers/                   # Provider 实现
│   │   ├── guardrails/                  # 7 个护栏插件
│   │   └── capabilities/                # Embedding/Rerank/Image Encode
│   ├── api/                             # FastAPI 路由
│   │   ├── deps.py                      # 依赖注入
│   │   ├── routes/                      # 18 个路由模块
│   │   └── schemas/                     # 请求/响应 Schema
│   ├── auth/                            # 认证授权
│   │   ├── middleware.py                # Auth 中间件
│   │   ├── deps.py                      # 认证依赖
│   │   ├── models.py                    # 权限模型
│   │   ├── permissions.py               # 权限检查
│   │   ├── token_manager.py             # Token 管理
│   │   └── prompts/                     # 多租户 Prompt 隔离
│   ├── core/                            # 基础设施
│   │   ├── config.py                    # Settings (三级优先级)
│   │   ├── exceptions.py                # 异常定义
│   │   ├── logger.py                    # 日志配置
│   │   ├── circuit_breaker.py           # 熔断器
│   │   ├── connections/                 # 连接管理
│   │   └── prompt_registry/             # Prompt 版本管理
│   ├── streaming/                       # Block E: SSE 流式
│   │   ├── event_bus.py                 # EventBus (asyncio.Queue Pub/Sub)
│   │   └── models.py                    # SseEvent + EVENT_TYPES
│   ├── session_history/                 # Block E: 会话历史
│   │   ├── service.py                   # SessionHistoryService
│   │   ├── repository.py                # SessionRepository
│   │   ├── search.py                    # SessionSearchService
│   │   ├── exporter.py                  # SessionExporter
│   │   ├── summarizer.py                # SessionSummarizer
│   │   ├── cleanup.py                   # SessionCleanupPolicy
│   │   ├── compressor.py                # ContextCompressor
│   │   └── memory_retriever.py           # MemoryRetriever
│   ├── document_management/             # Block E: 文档管理（上传自动入图）
│   ├── web_indexing/                    # Block E: Web 资源索引 + URL 文档
│   ├── integrations/                    # Block E: 集成生态
│   ├── batch/                           # Block E: 批量/定时任务
│   ├── observability/                   # Block E: 观测性
│   ├── models/                          # SQLAlchemy ORM 模型
│   └── security/                        # Block A: 数据安全
├── contracts/
│   ├── __init__.py
│   ├── interfaces.py                    # 跨 Layer 接口 + 数据模型
│   └── models.py                        # Block F 新增模型
├── docs/
│   ├── block-A-infrastructure.md        # 块 A 设计文档
│   ├── block-B-knowledge-layer.md       # 块 B 设计文档
│   ├── block-C-agent-pipeline.md        # 块 C 设计文档
│   ├── block-D-orchestration.md         # 块 D 设计文档
│   ├── block-E-enterprise.md            # 块 E 设计文档
│   ├── block-F-production-hardening.md  # 块 F 设计文档
│   ├── block-G-langgraph-advanced-patterns.md  # 块 G 设计文档
│   ├── deep-review-fix-plan.md          # 全链路深挖+重构方案
│   ├── phase-prompts.md                 # 各 Phase Prompt
│   └── full-architecture-deep-dive.md   # 本文档
├── scripts/                             # 工具脚本
├── storage/                             # 文件存储目录
├── tests/
│   ├── conftest.py                      # Pytest 配置
│   ├── test_lint.py                     # Lint 检查
│   ├── test_tech_stack_compliance.py    # 技术栈合规
│   ├── unit/                            # 单元测试
│   ├── integration/                     # 集成测试
│   ├── e2e/                             # 端到端测试
│   └── fixtures/                        # 测试数据
├── alembic.ini                          # Alembic 配置
├── docker-compose.yml                   # Docker 服务编排
├── Dockerfile                           # 应用 Docker 镜像
├── pyproject.toml                       # Python 项目配置
├── requirements.txt                     # Python 依赖
├── prometheus.yml                       # Prometheus 配置
├── tech-stack.yml                       # 技术栈声明（唯一真相来源）
├── README.md                            # 项目说明
├── DEVELOPMENT_GUIDE.md                 # 开发铁律
├── VIBE_CODING_RULES.md                 # Vibe 编码规则
├── overview.md                          # 开发记录
├── grill-self-review.md                 # 自省记录
└── prd2tsd.prd.md                       # 原始 PRD 设计稿
```

---


---

---

## 附篇 Q：关键技术术语表

| 术语 | 英文 | 含义 |
|------|------|------|
| 主编排图 | Orchestrator Graph | LangGraph StateGraph，串联4个Agent Layer的主图 |
| 适配器 | Adapter | 做 OrchestratorState ↔ LayerState 映射的中间层 |
| 条件边 | Conditional Edge | LangGraph 中根据 State 决定下一跳的边 |
| 中断恢复 | Interrupt/Resume | LangGraph 的 Human-in-the-Loop 机制 |
| 检查点 | Checkpoint | LangGraph 自动保存的中间状态，存入 PostgresSaver |
| 护栏 | Guardrail | LLM 调用前后的安全检查插件 |
| 熔断器 | Circuit Breaker | 连续失败后自动熔断的保护机制 |
| 故障转移 | Failover | Provider 不可用时自动切换到备用 Provider |
| 反思裁判 | ReflectionJudge | 知识检索后 LLM 判断检索质量并修正查询 |
| 倒数排名融合 | RRF (Reciprocal Rank Fusion) | 多路检索结果的融合算法 |
| 上下文压缩 | Context Compression | Token 超限时自动压缩历史消息 |
| 结构化输出 | Structured Output | 使用 PydanticOutputParser 让 LLM 输出 JSON Schema |
| 流式推送 | SSE (Server-Sent Events) | 服务端向客户端单向推送事件流 |
| 事件总线 | EventBus | 基于 asyncio.Queue 的 Pub/Sub 事件系统 |
| 函数调用 | Function Calling | LLM 自主选择工具的能力 |
| 节点内路由 | Command() | LangGraph 节点内部直接决定下一跳 |
| 并行扇出 | Send() Fan-Out | 将一个 State 同时发送给多个并行节点 |
| 子图 | Subgraph | 编译后的 StateGraph 作为另一个图的节点 |
| 线程ID | thread_id | LangGraph checkpoint 的唯一标识，绑定到 sessions 表 |
| 意图分类 | Intent Classify | 规则+LLM 双保险判断用户输入类型 |
| 迭代决策 | Iteration Decision | 根据评分决定接受/重规划/重生成/人工介入 |
| 评分校准 | Score Calibration | 历史比对+平行评测+反馈闭环的校准策略 |
| 多租户 | Multi-Tenant | 工作空间级别隔离，三级 Prompt 回退 |
| 数据脱敏 | Data Masking | LLM 调用前自动脱敏 L3/L4 级数据 |

---


---

---

## 附篇 R：参考资源

### 官方文档
- LangGraph: https://langchain-ai.github.io/langgraph/
- LangChain: https://python.langchain.com/
- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy 2.0: https://docs.sqlalchemy.org/en/20/
- Neo4j Python Driver: https://neo4j.com/docs/python-manual/current/
- PGVector: https://github.com/pgvector/pgvector
- OpenTelemetry: https://opentelemetry.io/docs/languages/python/

### 项目文件索引
- 原始设计: `prd2tsd.prd.md`
- 开发记录: `overview.md`
- 技术栈声明: `tech-stack.yml`
- 开发铁律: `DEVELOPMENT_GUIDE.md`
- 架构重构方案: `docs/deep-review-fix-plan.md`
- Copilot 指令: `.github/copilot-instructions.md`
- 各块设计: `docs/block-*.md`
- 本文档: `docs/full-architecture-deep-dive.md`

---

> **全文档真正结束** — 本文档共覆盖 PRD2TSD Agents 项目的：
> - 17 个主章节（系统概述 → 面试要点）
> - 17 个附篇（API 清单、数据模型、Docker 拓扑、代码规范、测试体系、
>   故障排查、演进时间线、业界对比、面试问答、节点代码模板、配置示例、
>   开发铁律、未来方向、目录结构、术语表、参考资源）
> - 总计约 5000 行
>
> **建议使用方式：**
> 1. 第一遍：通读第一章到第八章，建立系统全景认知
> 2. 第二遍：精读第九章主线任务全链路，理解每一步的数据流
> 3. 第三遍：按需查阅第十到十七章的具体链路
> 4. 面试前：重点看第十七章面试要点和附篇 J 的问答模板
> 5. 开发时：参考附篇 K 的代码模板和附篇 M 的开发铁律


---

---

## 附篇 S：快速查找索引

### 按模块查找
- 基础设施层 (Block A) → 第二章
- 知识层 (Block B) → 第三章
- Agent 流水线层 (Block C) → 第四章
- 主编排层 (Block D) → 第五章
- 企业级功能层 (Block E) → 第六章
- 生产级加固层 (Block F) → 第七章
- 高级模式增强 (Block G) → 第八章

### 按链路查找
- 主线任务全链路 (complex_generation) → 第九章
- 简单对话链路 (chat) → 第十章 §10.1
- 知识库查询链路 (knowledge_qa) → 第十章 §10.2
- 断点恢复链路 (interrupt/resume) → 第十一章
- 崩溃恢复场景 → 第十一章 §11.2
- 历史消息处理链路 → 第十二章
- SSE 流式推送链路 → 第十三章
- LLM 调用全链路 (Gateway + LangChain) → 第十四章

### 按面试主题查找
- LangGraph vs LangChain 分工 → 第十五章
- 为什么不用纯 LangChain → 第十五章 §15.3、附篇 J Q1
- PostgresSaver vs MemorySaver → 附篇 J Q2
- Adapter 模式设计原因 → 附篇 J Q3
- 护栏系统设计考量 → 附篇 J Q4
- 并发处理策略 → 附篇 J Q5
- 检索反思机制 → 附篇 J Q6
- Interrupt/Resume 实现 → 附篇 J Q7
- 最大技术挑战 → 附篇 J Q8
- 核心卖点总结 → 第十七章
- 业界方案对比 → 附篇 I

### 按代码模板查找
- Analysis Layer 节点模板 → 附篇 K §K.1
- Planning Layer 节点模板 → 附篇 K §K.2
- Generation Layer 节点模板 → 附篇 K §K.3
- Evaluation Layer 节点模板 → 附篇 K §K.4
- GatewayChatModel 使用模板 → 第十四章 §14.2
- Adapter 实现模板 → 第五章 §5.3
- EventBus 使用模板 → 第十三章 §13.1

### 按配置查找
- .env 完整示例 → 附篇 L §L.1
- pyproject.toml 配置 → 附篇 L §L.2
- prometheus.yml 配置 → 附篇 L §L.3
- Docker Compose 拓扑 → 附篇 C

### 按数据库表查找
- users 表 → 第二章 §2.3.1
- workspaces 表 → 第二章 §2.3.1
- sessions 表 → 第二章 §2.3.1 + 第六章 §6.2
- session_messages 表 → 第二章 §2.3.1
- llm_call_logs 表 → 第二章 §2.3.1
- langgraph_checkpoints 表 → 第五章 §5.2 + 第八章 §8.5

### 按 API 端点查找
- 完整 API 路由清单 → 附篇 A
- POST /api/v1/interact 详解 → 第九章 Step 1
- GET /api/v1/tasks/{id}/events 详解 → 第十三章 §13.2
- POST /api/v1/review/{id}/{stage} 详解 → 第九章 节点 4.6

### 按故障场景查找
- 任务不推进 → 附篇 G §G.1
- LLM 返回空 → 附篇 G §G.2
- SSE 连接断开 → 附篇 G §G.3
- 知识检索无结果 → 附篇 G §G.4
- 会话续接失忆 → 附篇 G §G.5

---


---

---

## 附篇 T：关键数字速查

| 指标 | 数值 |
|------|------|
| 总 Agent Layer 数 | 4 (Analysis / Planning / Generation / Evaluation) |
| 总节点数 | 43 (11+12+8+9 个节点 + 主编排 3 个路由节点) |
| 总 API 路由模块数 | 18 |
| 总数据库表数 | 12+ (users, orgs, workspaces, roles, team_members, sessions, session_messages, llm_call_logs, budget_configs, documents, web_resources, image_chunks, comments, suggestions, changelog) |
| 护栏插件数 | 7 (pre_llm: 3, post_llm: 4) |
| SSE 事件类型数 | 14 |
| 评测维度数 | 10 |
| 迭代最大轮数 | 3 |
| 标准方案章节数 | 14 |
| 函数最大行数 | 50 |
| 文件最大行数 | 300 |
| 类最大行数 | 200 |
| JWT access_token 有效期 | 15 分钟 |
| JWT refresh_token 有效期 | 7 天 |
| SSE keepalive 间隔 | 30 秒 |
| EventBus queue maxsize | 128 |
| Failover 健康检测间隔 | 60 秒 |
| CircuitBreaker 默认 failure_threshold | 3 次 |
| CircuitBreaker 默认 recovery_timeout | 30 秒 |
| Embedding 维度 | 1024 (BAAI/bge-large-zh-v1.5) |
| 文档上传最大大小 | 50 MB |
| Free 计划会话保留 | 30 天 |
| Pro 计划会话保留 | 180 天 |
| 知识图谱刷新频率 | 每 24 小时 |
| 会话清理频率 | 每小时 |
| Web 资源同步频率 | 每 2 小时 |
| 评测通过分数 | ≥ 85 |
| 评测触发回退分数 | < 70 |
| 预算降级阈值 | 月预算 90% |

---

> **全文结束**
> 文档路径: docs/full-architecture-deep-dive.md
> 总行数: ~5000+
> 覆盖范围: 全架构 + 全模块 + 全链路 + 全API + 全数据模型 + 全配置 + 全测试 + 全故障排查 + 全面试问答