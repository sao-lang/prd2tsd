# PRD2TSD Agents — 全链路架构与运行时深度解析

> **版本**: v3.0
> **日期**: 2026-08-14
> **目标读者**: 系统架构理解、新成员 onboarding、全链路故障排查
> **状态**: 基于 2026-08-13 代码库真实状态重写（含 WP1 观测 / WP2 评测 / Block E 整改 / 社区检测简化）
>
> **注意**: 本文档为项目唯一全链路架构文档，覆盖**所有功能模块与运行时链路**。
> 面试相关章节已迁移至 `docs/interview-questions.md`。

---

## 目录

- [一、系统概述](#一系统概述)
- [二、基础设施层（Block A）](#二基础设施层block-a)
- [三、知识层（Block B）](#三知识层block-b)
- [四、Agent 流水线层（Block C）](#四agent-流水线层block-c)
- [五、主编排层（Block D）](#五主编排层block-d)
- [六、企业级功能层（Block E）](#六企业级功能层block-e)
- [七、生产级加固层（Block F）](#七生产级加固层block-f)
- [八、评测与观测层（WP1/WP2）](#八评测与观测层wp1wp2)
- [九、主线任务全链路逐节点详解](#九主线任务全链路逐节点详解)
- [十、chat / knowledge_qa / clarification 路径全链路](#十chat--knowledge_qa--clarification-路径全链路)
- [十一、document_analysis / URL 文档路径全链路](#十一document_analysis--url-文档路径全链路)
- [十二、断点恢复与 Human-in-the-Loop 全链路](#十二断点恢复与-human-in-the-loop-全链路)
- [十三、历史消息处理全链路](#十三历史消息处理全链路)
- [十四、SSE 流式推送全链路](#十四sse-流式推送全链路)
- [十五、LLM 调用全链路（Gateway + LangChain 适配器）](#十五llm-调用全链路gateway--langchain-适配器)
- [十六、LangGraph 与 LangChain 的分工设计](#十六langgraph-与-langchain-的分工设计)
- [十七、关键技术决策与架构原则](#十七关键技术决策与架构原则)
- [十八、API 端点完整清单](#十八api-端点完整清单)
- [十九、数据模型与数据库](#十九数据模型与数据库)
- [二十、Docker 拓扑与配置](#二十docker-拓扑与配置)
- [二十一、已知问题与风险](#二十一已知问题与风险)
- [二十二、术语表与关键数字速查](#二十二术语表与关键数字速查)

---

## 一、系统概述

### 1.1 一句话定义

**PRD2TSD Agents** 是一个基于 **LangGraph + LangChain Core** 的 **Multi-Agent 系统**，输入产品需求文档（PRD），经过 **知识检索 → 需求分析 → 架构规划 → 方案生成 → 质量评测** 五步流水线，自动输出完整的技术方案文档（TSD）。附带企业级的 **多租户权限、SSE 流式推送、护栏安全、熔断降级、记忆增强、评测闭环** 等生产级能力。

### 1.2 核心价值

| 价值维度 | 描述 |
|---------|------|
| **自动化** | 将数天的人工方案编写缩短到分钟级 |
| **标准化** | 14 章节标准化输出，确保方案文档质量一致 |
| **可迭代** | Evaluation 评分 < 阈值自动回退重规划/重生成，最多 3 轮迭代 |
| **可审核** | Human-in-the-Loop 机制，分析/规划节点人工确认 |
| **可恢复** | PostgreSQL Checkpointer 持久化，崩溃后可断点续传 |
| **可观测** | OpenTelemetry 全链路追踪（HTTP→节点→LLM）+ Prometheus 指标 + Grafana + SSE 实时推送 |
| **可评测** | ragas RAG 评测（L1/L2 指标 + 反思 A/B）+ Agent 评测（L3 过程 + L4 结果 rubric） |
| **企业级** | RBAC/ABAC 权限、多租户隔离、数据脱敏、预算控制、审计日志、Webhook |

### 1.3 技术栈全景（以实际代码为准）

```text
Agent 编排:      LangGraph 1.2+（StateGraph + PostgresSaver Checkpointer）
Agent 节点内部:   LangChain Core（ChatPromptTemplate + PydanticOutputParser + GatewayChatModel）
LLM 接入:        自研 LLM Gateway（OpenAI SDK 兼容多 Provider + 7 护栏 + 熔断 + Failover + 缓存）
Web 框架:        FastAPI 0.110+ (async)
ORM/迁移:        SQLAlchemy 2.0 (async) + Alembic
数据库:          PostgreSQL 15（PGVector 向量检索）
图数据库:        Neo4j 5.x（知识图谱，compose 端口 7700/7701）
缓存/队列:       Redis 7.x（Celery 任务队列 broker）
对象存储:        MinIO（文档存储）
Embedding:      BAAI/bge-large-zh-v1.5 (1024d) / text-embedding-3-small（API）
Rerank:         BAAI/bge-reranker-v2-m3（本地）/ cohere-rerank（API）
文档入图:        multi_format_loader（pdf/csv/docx/md/txt/图片）
追踪:           OpenTelemetry → Jaeger（OTLP gRPC）
指标:           Prometheus → Grafana
评测:           ragas 0.4.3（RAG）+ rubric judge（Agent）
LLM 模型:       DeepSeek-V3（主）/ GPT-4o-mini（降级/Judge）
任务队列:        Celery 5.3+（worker + beat）
测试/Lint:      Pytest + Ruff + Mypy
```

### 1.4 系统分层架构

```text
┌──────────────────────────────────────────────────────────────┐
│  用户交互层:  FastAPI REST / SSE（POST /api/v1/interact 统一入口）│
├──────────────────────────────────────────────────────────────┤
│  主编排层:    LangGraph Orchestrator（StateGraph）            │
│              classify → chat/retrieve/clarify/复杂生成分流     │
│              → 知识检索 → 4层Agent → 迭代决策 → 记忆压缩 → 保存 │
│              + Human-in-the-Loop / PostgresSaver 断点恢复      │
├──────────────────────────────────────────────────────────────┤
│  Agent 层:    4 个独立 StateGraph                             │
│              Analysis(11) → Planning(14) → Generation(8)     │
│              → Evaluation(Send 并行 9)                       │
├──────────────────────────────────────────────────────────────┤
│  知识层:      实体增强双路检索 + ReflectionJudge 反思          │
│              多格式入图 → 分块 → 实体提取 → Neo4j 图 + PGVector │
├──────────────────────────────────────────────────────────────┤
│  企业增强:    SSE流式 │ 会话历史 │ 文档管理 │ 统一交互入口     │
│              URL文档(SSRF) │ 多格式入图 │ 批量任务 │ Webhook   │
├──────────────────────────────────────────────────────────────┤
│  生产加固:    7护栏 │ 熔断器 │ Failover链 │ 记忆增强 │         │
│              Prompt版本管理 │ 行为回放 │ 数据脱敏 │ 审计日志   │
├──────────────────────────────────────────────────────────────┤
│  观测评测:    OTel 全链路追踪 │ Prometheus/Grafana │          │
│              ragas RAG 评测 │ Agent rubric 评测              │
├──────────────────────────────────────────────────────────────┤
│  基础设施:    PostgreSQL+PGVector │ Neo4j │ Redis │ MinIO    │
│              LLM Gateway │ Jaeger │ Prometheus │ Grafana     │
└──────────────────────────────────────────────────────────────┘
```

### 1.5 模块目录全景（实际代码结构）

```text
app/
├── main.py                  # FastAPI 入口 + lifespan + 中间件 + 路由注册
├── task_manager.py          # 异步任务管理器（in-memory + EventBus + 指标埋点）
├── api/                     # FastAPI 路由（15 个路由模块） + schemas + deps
├── orchestrator/            # Block D：主编排（main_graph/state/runtime/adapters/nodes）
├── analysis_layer/          # Block C1：需求分析（11 节点）
├── planning_layer/          # Block C2：架构规划（14 节点 + 回退循环）
├── generation_layer/        # Block C3：方案生成（8 节点 + Send 扇出 + Jinja2 模板）
├── evaluation/              # Block C4：评测（Send 并行 9 节点）+ rag/ + agent/ 评测闭环
├── knowledge_layer/         # Block B：知识层（ingestion/ + retrieval/ + 图/向量存储）
├── llm_gateway/             # Block A：LLM Gateway（providers/guardrails/capabilities/适配器）
├── auth/                    # Block A：认证授权（JWT + RBAC/ABAC + 多租户 Prompt）
├── security/                # Block A：数据安全（L1-L4 分类/脱敏/审计哈希链）
├── models/                  # SQLAlchemy ORM 模型
├── core/                    # 基础设施（config/circuit_breaker/exceptions/logger/connections/prompt_registry）
├── streaming/               # Block E：SSE（event_bus/models/sse 工具）
├── session_history/         # Block E：会话历史（service/search/export/压缩/记忆检索）
├── document_management/     # Block E：文档管理（MinIO 存储/去重/预览/搜索/入图触发）
├── web_indexing/            # Block E：Web 索引（loader/crawler/sync + url_security/url_document）
├── integrations/            # Block E：Webhook
├── batch/                   # Block E：Celery 定时/批量任务
├── observability/           # WP1：观测（metrics/tracing/replay 行为回放）
├── agents/tools/            # ⚠️ 已废弃（ToolRegistry 零调用，待 LangChain ToolNode 替代）
└── container.py             # 不存在（本项目无 container，依赖通过 api/deps 注入）
contracts/                   # 跨层数据模型（interfaces.py + models.py）
```

---

## 二、基础设施层（Block A）

### 2.1 模块清单

| 模块 | 目录 | 核心文件 |
|------|------|---------|
| 数据库模型 | `app/models/` | SQLAlchemy ORM（users/workspaces/roles/sessions/uploaded_documents 等 10 表） |
| 认证授权 | `app/auth/` | JWT 双 token、RBAC/ABAC 权限、FastAPI 中间件、多租户 Prompt |
| 连接管理 | `app/core/connections/` | PostgreSQL/Redis/MinIO/Neo4j 生命周期管理 |
| 配置中心 | `app/core/config.py` | pydantic-settings 三级优先级配置 |
| LLM Gateway | `app/llm_gateway/` | Provider 抽象、模型路由、成本追踪、语义缓存、护栏、熔断、Failover |
| 数据安全 | `app/security/` | 数据分级（L1-L4）、脱敏引擎、哈希链审计日志 |
| 熔断器 | `app/core/circuit_breaker.py` | 通用异步熔断器（CLOSED/OPEN/HALF_OPEN） |
| Prompt 版本管理 | `app/core/prompt_registry/` | Prompt 版本存储/回滚/A-B 测试配置 |
| Contracts | `contracts/` | 跨 Layer 接口和数据模型定义 |
| 数据库迁移 | `alembic/` | 3 个版本化迁移 |

### 2.2 数据库模型（10 张表）

> 详见第十九章。核心表：`users / organizations / workspaces / roles / team_members / llm_call_logs / budget_configs / sessions / session_messages / uploaded_documents`。
> **注意**：项目**没有**独立的 `documents` / `web_resources` / `image_chunks` 表——文档实体统一为 `uploaded_documents`；Web 资源不落 SQLAlchemy，抓取内容增量写入知识图谱（Neo4j + PGVector），URL 变更跟踪由 `WebSyncScheduler` 内存 dict 维护。

### 2.3 认证授权架构

#### 2.3.1 JWT 双 Token 机制

```text
access_token (15分钟, HS256) + refresh_token (7天)
     │
     ├─ 注册/登录: POST /api/v1/auth/register|login → 返回双 token（含 org_id/ws_id/permissions）
     ├─ 访问:      Authorization: Bearer {access_token}
     ├─ 刷新:      POST /api/v1/auth/refresh → 校验 type=="refresh" 后签发新 access
     └─ 登出:      POST /api/v1/auth/logout → 客户端清 token（无黑名单）
```

- `TokenManager`：`create_access_token(user_id, org_id, ws_id, permissions)`（payload: sub/org_id/ws_id/permissions/exp/iat/jti/type="access"）；`create_refresh_token(user_id)`（type="refresh"）
- `AuthMiddleware`：从 `Authorization: Bearer` 提取 JWT → `verify_token()` 解析 → 写入 `request.scope`（`auth.user_id` / `auth.org_id` / `auth.ws_id` / `auth.permissions`，未认证预置默认值）
- `WorkspaceContextMiddleware`：仅当 JWT 未携带 `ws_id` 时才从 `X-Workspace-ID` 头或 `ws_id` 查询参数提取；**不可覆盖 Token 中已认证的 ws_id**（防越权）
- 中间件顺序：`CORS → AuthMiddleware → WorkspaceContextMiddleware → http_tracing_middleware`

#### 2.3.2 RBAC + ABAC 混合权限

```text
权限模型（app/auth/permissions.py）:
  SYSTEM_PERMISSIONS:
    admin :  workspace:create/read/update/delete/manage_members, prd:create/read/update/delete, model_config:read/update
    editor:  workspace:read, prd:create/read/update
    viewer:  workspace:read, prd:read

  PermissionChecker:
    check_permission()       精确匹配
    check_workspace_access() 基于 workspace 列表
    has_any_permission()     OR 组合

  依赖注入:  require_permission(permission) → 失败抛 PermissionDeniedError(403)
```

#### 2.3.3 多租户 Prompt 隔离（app/auth/prompts/）

```text
PromptManager.get_prompt(org_id, agent_name, node_name, extra_vars):
  1. 精确匹配（org + agent + node）
  2. Agent 级通配（org + agent + "*"）
  3. 系统默认兜底（DEFAULT_PROMPTS: analysis:requirement / planning:pattern / generation:outline / evaluation:scoring）

PromptRenderer:  Jinja2 Template.render(**variables)
PromptStore:     ⚠️ 当前为内存实现（dict），未接数据库
```

### 2.4 LLM Gateway 核心架构

> 详细调用链路见第十五章。本节给架构总览。

#### 2.4.1 设计目标

将多模型调用统一为一个门面（`app/llm_gateway/__init__.py` 的 `LLMGateway` 类，全局单例 `gateway`）：

| 能力 | 实现 |
|------|------|
| Provider 抽象 | `providers/`：OpenAI / Anthropic / Cohere / Custom，经 `ProviderFactory` 创建 |
| 模型路由 | `config_manager.resolve_model(task_type)`（按 task_type → model_type/provider/model） |
| 成本追踪 | `cost_tracker.record()` → llm_call_logs 语义 + `LLM_COST_TOTAL` 指标 |
| 语义缓存 | `cache.py`：SHA-256(prompt+task_type) 精确匹配，TTL 1h，max 1000 条 |
| 速率限制 | `rate_limiter.py`：RPM（默认 60）/ TPM（默认 100000）滑动窗口，按 workspace |
| 预算控制 | `budget_controller.py`：月预算超 90% 自动降级到低成本模型 |
| 熔断 | 每个 Provider 独立 `CircuitBreaker`（failure_threshold=3, recovery_timeout=30s） |
| Failover | LLM 链：deepseek-chat → gpt-4o-mini；每 60s 健康检测 |
| 护栏 | 7 个可插拔护栏（详见第七章） |

#### 2.4.2 配置三级优先级

```text
运行时注入（ModelConfigManager._runtime_config，API PUT /model-config 动态更新，最高优先级）
    ↓
环境变量（MODEL_CONFIG__<TYPE>__<PROVIDER>__API_KEY 等）
    ↓
代码默认值（最低优先级）

路由规则示例（MODEL_ROUTING__* 环境变量）:
  analysis.requirement → llm/deepseek/deepseek-chat
  planning.architecture → llm/deepseek/deepseek-chat
  evaluation.scoring   → judge/openai/gpt-4o-mini
  generation           → llm/deepseek/deepseek-chat
  embedding            → embedding/openai/text-embedding-3-small
  rerank               → rerank/cohere/rerank-english-v3.0
```

#### 2.4.3 支持的模型类型

```text
model_types: llm / embedding / rerank / judge / vision
  llm:       deepseek-chat（主）、gpt-4o-mini（降级）
  embedding: text-embedding-3-small（API） + BAAI/bge-large-zh-v1.5（本地兜底）
  rerank:    cohere-rerank-english-v3.0（API） + BAAI/bge-reranker-v2-m3（本地）
  judge:     gpt-4o-mini（评测用低成本模型）
  vision:    gpt-4o（已弃用 CLIP 多模态，仅配置保留）
```

> **⚠️ 注意**：`app/llm_gateway/router.py` 的 `ModelRouter` **已废弃**（DeprecationWarning），功能合并到 `ModelConfigManager`。

### 2.5 连接管理（app/core/connections/）

```text
ConnectionManager（全局单例 connection_manager）:
  register(name, connector) / get(name) / startup() / shutdown() / health_check()
  关闭顺序: Neo4j → MinIO → Redis → PostgreSQL

  PostgreSQLConnector: asyncpg + SQLAlchemy async engine，pool_size=10, max_overflow=20
  RedisConnector:      redis-py async client
  MinIOConnector:      minio client（同步，经 asyncio.to_thread 包装）
  Neo4jConnector:      neo4j async driver
  init_connections():  注册 4 个连接器（enabled 由配置控制）
```

### 2.6 数据安全架构（app/security/）

```text
数据分级（DataLevel）:
  L1 公开:  email、ip_address（无需处理）
  L2 内部:  password、phone（脱敏）
  L3 敏感:  api_key(sk-/pk-/coh-)、token/jwt/bearer、id_card（严格脱敏+审计）
  L4 机密:  最高等级（脱敏+审计+加密的预留）

DataClassifier.classify(text): 正则检测 → 返回最高等级
DataMaskingEngine.mask(text, level="L2"):
  只脱敏当前等级及以下的模式，替换为 [MASKED_API_KEY] 等标记
  经 get_masking_engine() 单例注入（api/deps.py）

审计日志（AuditLogger）:
  AuditLogEntry 哈希链: 每个条目标记 prev_hash，verify_hash_chain() 校验不可篡改
```

### 2.7 通用熔断器（app/core/circuit_breaker.py）

```text
状态机: CLOSED →(连续失败 N 次)→ OPEN →(等待超时)→ HALF_OPEN →(试探成功)→ CLOSED
                                              └→(试探失败)→ OPEN

默认参数: failure_threshold=5, recovery_timeout=30s, half_open_max_requests=1
Gateway 中 Provider 熔断:  name="provider:<name>", failure_threshold=3, recovery_timeout=30
用法:  await circuit_breaker.call(fn, *args, **kwargs)
```

### 2.8 认证授权链路（注册 / 登录 / 鉴权全链路）

#### 2.8.1 注册链路

```text
POST /api/v1/auth/register { email, password, display_name }
  → 密码哈希（passlib[bcrypt]）
  → 创建 User（auth_provider="jwt"）
  → 自动创建 Organization + 个人 Workspace + admin Role + TeamMember
  → 签发双 token: create_access_token(user_id, org_id, ws_id, permissions)
                 + create_refresh_token(user_id)
  → 返回 TokenResponse{access_token, refresh_token, token_type="bearer", expires_in=900}
```

#### 2.8.2 登录 / 刷新 / 登出链路

```text
POST /auth/login       → 校验密码 → 签发双 token（携带 org_id/ws_id/permissions）
POST /auth/refresh     → 校验 refresh_token（type=="refresh"）→ 签发新 access_token
POST /auth/logout      → 客户端清 token（无服务端黑名单）
GET  /auth/me          → 返回当前用户信息
```

#### 2.8.3 请求鉴权链路（每个 /api/v1/* 请求）

```text
HTTP 请求
  │
  ▼
① AuthMiddleware（BaseHTTPMiddleware）
  │  Authorization: Bearer <access_token>
  │  → token_manager.verify_token() 验签 + 过期检查
  │  → 写入 request.scope: auth.user_id / auth.org_id / auth.ws_id / auth.permissions
  │     （未携带 token 时预置默认值 "" / []，不强制拦截）
  ▼
② WorkspaceContextMiddleware
  │  仅当 scope 无 ws_id 时：从 X-Workspace-ID 头 / ws_id 查询参数提取
  │  不可覆盖 Token 中已认证的 ws_id（防越权）
  ▼
③ http_tracing_middleware
  │  读 scope 的 auth.user_id 写入 http span attribute（见第八章 8.6）
  ▼
④ 路由处理（依赖注入）
  │  Depends(get_current_user)     → 读 auth.user_id，空则 401
  │  Depends(get_current_workspace)→ 读 auth.ws_id，空则 400
  │  Depends(require_permission("prd:read")) → PermissionChecker.check_permission
  │       → 精确匹配用户 permissions → 不通过抛 PermissionDeniedError(403)
  ▼
⑤ 业务逻辑（TenantContext 贯穿）
```

---

## 三、知识层（Block B）

### 3.1 概述

知识层是系统的数据底座，构建**实体增强的双路检索**系统：多格式文档入图 → 分块 + 实体提取 → 双路检索 + 反思纠偏。所有后续 Agent Layer 的分析和规划都依赖本块的检索能力。

### 3.2 核心设计：双路检索架构（简化后的现状）

```text
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
    Neo4j 图 +    实体按类型聚合    双路 + RRF
    PGVector        + LLM 宏观总结
          │            │            │
          └────────────┼────────────┘
                       ▼
              ┌─────────────────┐
              │   ReflectionJudge│ ← LLM 判断检索质量，refine 则修正查询重检索
              │   （最多 3 轮）   │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │     ReRanker    │ ← Cross-encoder 精排（bge-reranker 或 LLM）
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │    Compressor   │ ← 4000 token 预算去冗余
              └────────┬────────┘
                       ▼
                 RetrievalContext
```

> **版本变更**：社区检测（Leiden/CommunityReport）已按用户要求简化删除（WP3），
> Global Search 保留"实体按类型聚合 + LLM 宏观总结"的轻量实现；
> `RetrievalContext.community_summary` 已改名为 `global_summary`。

### 3.3 知识图谱构建流程

```text
多格式文档（.md/.txt/.csv/.tsv/.docx/.pdf/图片）
    │
    ▼
DocumentLoader.load(file_path)          # 仅 .md（构建器主路径）
  或 multi_format_loader.extract_text() # 多格式字节流提取（上传/URL 路径）
    │
    ▼
MultiGranularityChunker.chunk(text, level)
    │  三级分块:
    │  sentence:   50 字/块（按 。！？\n 切，超长再按 ，； 切）
    │  paragraph:  500 字/块（按空行切）
    │  section:    按 Markdown #{1,3} 标题切，section_path="<level> <title>"
    │
    ▼
EntityExtractor.extract(chunks)
    │  逐 chunk 调 gateway.complete（temperature=0.1, max_tokens=2048, 前 2000 字）
    │  实体类型(5种): TechStack / Component / ArchitecturePattern / Constraint / Concept
    │
    ▼
EntityResolver.resolve_batch(new_entities, existing)
    │  两级消歧: ① 精确名称匹配 ② ALIAS_MAP 别名表 + MD5 归一化 key（去 -_ 空格）
    │  _merge_entities: 保留更长描述、取 max confidence、合并 properties
    │
    ▼
EntityEmbedder.embed_entity(entity)
    │  双源融合: 名称 embedding×0.5 + 描述 embedding×0.5（加权平均）
    │  模型: BAAI/bge-large-zh-v1.5 (1024d)，API 优先 → 本地兜底 → 零向量
    │
    ▼
Neo4j 写入（KGEntity 节点）+ PGVector 写入（entity_embeddings）
    │
    ▼
ClaimsExtractor.extract(chunks)         # Block F: 决策断言提取（5 种类型）
    │  逐 chunk 调 gateway.complete，source_text_unit_id=chunk.id
    ▼
PGVector 写入（claim_embeddings）
    │
    ▼
BuildStats { entities, chunks, file_path, workspace_id }
```

**三条构建入口**：

| 入口 | 方法 | 说明 |
|------|------|------|
| 文件路径 | `KnowledgeGraphBuilder.build_from_document(file_path, workspace_id)` | 9 步完整流程（含 Claims） |
| 文本 | `KnowledgeGraphBuilder.build_from_text(text, source_name, workspace_id)` | 与上面一致，**少 Claims 步骤** |
| 字节流 | `KnowledgeGraphBuilder.build_from_bytes(content, filename, workspace_id)` | `multi_format_loader.extract_text` 提取后走 build_from_text；空文本抛 ValueError |

**多格式加载器（multi_format_loader.py）**：

```text
SUPPORTED_EXTENSIONS = {.md,.txt,.csv,.tsv,.docx,.pdf,.png,.jpg,.jpeg}
extract_text(content: bytes, filename: str) -> str:
  md/txt   → 直接 decode
  csv/tsv  → 每行转 "记录: a，b。"
  docx     → python-docx（段落 + 表格行）
  pdf      → pypdf（每页标 "[第 N 页]"）
  图片     → "[图片: {filename}, 类型, 大小 KB]"（仅元数据占位，多模态已删）
```

### 3.4 向量存储（app/knowledge_layer/vector_store.py）

```text
ensure_extensions(): 建 3 张表 text_unit_embeddings / entity_embeddings / claim_embeddings
                     （维度 kn_config.embedding_dimension=1024）
similarity_search(embedding, table, top_k, workspace_id):
  1 - (embedding <=> :vec)  cosine 相似度，表白名单校验
upsert_chunk / upsert_entity_embedding / upsert_claim: ON CONFLICT DO UPDATE
search_claims(query, top_k=5): ⚠️ 实际非向量检索（仅过滤 workspace_id + 时间倒序）
```

### 3.5 Local Search（本地搜索）详解

```text
用户查询 → QueryRewriter.rewrite() → LLM 生成 ≤5 条子查询（原始查询保证首位，失败回退 [query]）
        → QueryEnricher.enrich() → 正则抽关键词 → 每词 search_entities(limit=3)
                                    → 匹配则追加 "(entities: id1, id2, ...)"（最多 5 个）

LocalSearch.search():
  1. 关键词匹配实体（e.name CONTAINS）
  2. 对前 5 个中心实体 get_neighbors(max_depth=2)（Neo4j 子图遍历）
  3. 收集有 source_text_unit_id 的实体
  4. _assemble_context（查询 / 匹配实体 / 相关实体 / 原文来源 四段）

LocalSearch.search_as_docs():
  每个匹配实体 → ScoredDoc，分数 = 1.0 - i*0.1（纯位置降权）
  无结果时回退 context 单条（score 0.5）
```

### 3.6 Global Search（全局搜索）详解（社区检测已简化）

```text
GlobalSearch.search():
  1. get_all_entities(workspace_id)（Neo4j，上限 10000）
  2. _group_by_type: 按实体类型分组，取前 global_top_k=5 个类型（按实体数降序）
  3. GLOBAL_SUMMARY_PROMPT → LLM 宏观总结（entities_text 前 4000 字，temperature=0.3）

GlobalSearch.search_as_docs():
  返回单条 ScoredDoc(id="global_summary", score=1.0, source="global")

触发: 意图路由器 GLOBAL_KEYWORDS（整体/架构/概述/总结/architecture/overview...）
      → 判定 global；短查询(<5字) → local；默认 hybrid
```

### 3.7 检索反思（ReflectionJudge）

```text
ReflectionJudge.judge(query, results) -> ReflectionResult:
  { judgment: "accept"|"refine", reason, refined_query }
  无结果 → 直接 refine
  格式化前 5 条（每条 text 前 200 字）→ LLM 判断
  解析失败 → 默认 accept

反思循环（RetrievalPipeline.retrieve，max_reflection_rounds=2，最多 3 轮）:
  round 1: sub_queries[:3] 各跑 local_search + global → RRF 融合
  非末轮:   reflection.judge() → accept 则 break；refine 则 refined_query 重跑
```

### 3.8 RRF 融合 / 重排 / 压缩

```text
RRFFusion.fuse(*ranked_lists):
  score += 1 / (k + rank + 1)，k = 60；按非空列表数归一化

ReRanker.rerank(query, results, top_k):
  默认 Cross-encoder BAAI/bge-reranker-v2-m3（transformers 懒加载，pair 截 512 字）
  模型不可用 → _simple_rerank: doc.score = score*0.7 + keyword_coverage*0.3

Compressor.compress(results):
  max_tokens=4000 预算，按 token 顺序累加，最后一个文档截断
  token 估算: 中文 1.5 token/字 + 英文 0.25 token/字符
```

### 3.9 核心数据模型

```text
KGEntity:     id, name, type(5种), category, description, properties, embedding,
              confidence=0.9, source_text_unit_id, workspace_id
Claim:        id, subject, subject_entity_id, object, object_entity_id,
              claim_type(5种: comparison/decision/specification/constraint/prediction),
              content, confidence, source_text_unit_id, workspace_id
ScoredDoc:    id, text, score, source("local"/"global"/"hybrid"/"vector"), metadata
RetrievalContext: query, mode, results[ScoredDoc], matched_entities[KGEntity],
              text_unit_evidence[], global_summary="", total_tokens=0
Chunk:        id, text, level(sentence/paragraph/section), section_path, index, metadata
```

### 3.10 关键常量（app/knowledge_layer/config.py）

| 常量 | 值 |
|------|-----|
| embedding_model / dimension / device | `BAAI/bge-large-zh-v1.5` / 1024 / cpu |
| sentence_max_words / paragraph_max_words | 50 / 500 |
| local_top_k / global_top_k / hybrid_top_k | 10 / 5 / 10 |
| rrf_k | 60 |
| max_compress_tokens | 4000 |
| 老化 downgrade/archive/soft_delete_days | 90 / 180 / 365（当前无人调用） |

### 3.11 Protocol 接口边界（app/knowledge_layer/interfaces.py）

```text
6 个 Protocol: DocumentReader / TextChunker / TextEmbedder / QueryRewriterInterface /
               ResultFuser / ResultReranker
文档标注「当前不切换，仅抽离接口」——自实现是默认实现
```

### 3.12 知识图谱构建链路（Ingestion 全链路）

```text
入口 A: POST /documents/upload（文档上传）
  → 校验/去重 → MinIO 存储 → DB 写 uploaded_documents(processing_status=pending)
  → Celery index_document_to_kg(document_id)
      → 下载原始字节 → build_from_bytes → 更新 status(processing→indexed/failed)

入口 B: POST /knowledge/build（上传 .md）或 /knowledge/build-from-path
  → build_from_document(file_path)

入口 C: POST /web-indexing/fetch（URL 抓取）
  → WebLoader.fetch → 增量写入知识图谱

统一构建链路（KnowledgeGraphBuilder）:
  [多格式字节/文本]
    │
    ▼ multi_format_loader.extract_text() / DocumentLoader.load()
  [纯文本]
    │
    ▼ MultiGranularityChunker.chunk(level="paragraph")  # 50/500 字句段，按标题切 section
    │
    ▼ EntityExtractor.extract(chunks)   # 逐 chunk LLM，5 种实体类型
    │
    ▼ EntityResolver.resolve_batch()    # 精确匹配 + ALIAS_MAP 别名消歧
    │
    ▼ EntityEmbedder.embed_entity()     # 名称×0.5 + 描述×0.5，bge-large-zh-v1.5
    │
    ▼ 双写: Neo4j(KGEntity) + PGVector(entity_embeddings)
    │
    ▼ ClaimsExtractor.extract(chunks)   # （build_from_document 路径）
    │
    ▼ PGVector(claim_embeddings)
    │
    ▼ BuildStats{entities, chunks, file_path, workspace_id}
    │
    ▼ （入口 A）更新 uploaded_documents: entity_count / relation_count /
        indexed_at / processing_status
```

### 3.13 检索链路（查询全链路）

```text
入口: ① complex_generation → knowledge_retrieval 节点（mode=hybrid, top_k=10）
      ② knowledge_qa → retrieve_node（top_k=5）
      ③ POST /knowledge/search（mode: local/global/hybrid, top_k）
      ④ RagEvaluator（评测，mode=expected_mode, top_k=config）

RetrievalPipeline.retrieve(query, mode, top_k, workspace_id):
  [查询]
    │
    ▼ ① IntentRouter.route()     # 仅 hybrid 模式：GLOBAL/LOCAL 关键词 → 具体模式
    ▼ ② QueryRewriter.rewrite()  # LLM 生成 ≤5 条子查询（原查询保证首位）
    ▼ ③ QueryEnricher.enrich()   # 正则抽词 → search_entities → 追加实体 ID
    │
    ▼ ④ 反思循环（最多 3 轮）:
    │    ├─ local/hybrid: sub_queries[:3] → LocalSearch.search_as_docs()（Neo4j 子图 + 位置降权）
    │    ├─ global/hybrid: GlobalSearch.search()（实体按类型聚合 + LLM 宏观总结）
    │    └─ hybrid 且两路有结果 → RRFFusion.fuse(k=60)
    │       非末轮 → ReflectionJudge.judge() → accept 则 break；refine 用 refined_query 重跑
    │
    ▼ ⑤ ReRanker.rerank(query, results, top_k)   # bge-reranker 或 关键词降权回退
    ▼ ⑥ Compressor.compress()                    # 4000 token 预算
    │
    ▼ RetrievalContext{query, mode, results, matched_entities, global_summary, total_tokens}
    │
    ▼ 消费方: 注入 knowledge_context（节点） / 返回 API 响应 / RagEvaluator 评分
```

---

## 四、Agent 流水线层（Block C）

### 4.1 概述

4 个独立的 Agent Layer，每个 Layer 是一个 LangGraph StateGraph，可独立运行和测试，100% 通过 `contracts/interfaces.py` 解耦。所有节点经 `trace_node()` 包装（WP1 观测埋点）。

### 4.2 解耦设计原则

```text
C1 (Analysis)    输出 → AnalysisResultDetail
C2 (Planning)    输入 AnalysisResultDetail，输出 → PlanningResultDetail
C3 (Generation)  输入 PlanningResultDetail，输出 → GenerationResultDetail
C4 (Evaluation)  输入全部三个 Result，输出 → EvaluationReportDetail

❌ 禁止：C2 的 Node 直接 import C1 的 Node
❌ 禁止：任何 Layer 直接引用 OrchestratorState
✅ 允许：通过 contracts/models.py 共享数据模型
```

### 4.3 C1 — Analysis Layer（需求分析层，11 节点线性链）

```text
parse → lang_detect → requirement → constraint → dependency → domain
     → quality → effort → stakeholder → clarity → assemble → END
（全部 trace_node 包装，共享 GatewayChatModel(task_type="analysis", layer="analysis")）
```

| 节点 | 输入→输出 | LLM |
|------|----------|-----|
| `parse` (DocumentParserNode) | prd_raw → prd_sections（parse_markdown_sections） | 无 |
| `lang_detect` | prd_raw[:200] → 语言；en 则翻译 prd_raw[:8000]→中文覆盖 | ✅ |
| `requirement` | prd_raw[:8000] → extracted_requirements（失败回退 []） | ✅ |
| `constraint` | prd_raw[:6000] → extracted_constraints | ✅ |
| `dependency` | requirements → dependency_graph（无需求则空图） | ✅ |
| `domain` | prd_raw[:3000] → domain_tags（回退 ["通用"]） | ✅ |
| `quality` | requirements → confidence（score/10；失败 0.5） | ✅ |
| `effort` | requirements → 更新 confidence 均值（COCOMO II） | ✅ |
| `stakeholder` | prd_raw[:4000] → stakeholders | ✅ |
| `clarity` | requirements → clarity_issues | ✅ |
| `assemble` | 聚合 → analysis_result（Phase4 修复：消费 stakeholders+clarity_issues） | 无 |

**AnalysisState 关键字段**：`prd_raw, prd_sections, extracted_requirements, extracted_constraints, dependency_graph, domain_tags, analysis_result, confidence, stakeholders, clarity_issues` + Orchestrator 注入 `knowledge_context, system_prompt`。

**节点内部统一模式**（LangChain 结构化输出）：

```python
class RequirementExtractorNode:
    def __init__(self, llm=None):
        self.llm = llm or GatewayChatModel(task_type="analysis", layer="analysis",
                                           node="requirement_extractor")
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT), ("human", "PRD内容：\n{prd_text}")])
        self.parser = PydanticOutputParser(pydantic_object=RequirementList)
        self.chain = self.prompt | self.llm | self.parser   # LCEL 链

    async def run(self, state: AnalysisState) -> AnalysisState:
        result: RequirementList = await self.chain.ainvoke({"prd_text": state["prd_raw"][:8000]})
        state["extracted_requirements"] = [RequirementDetail(**r.dict()) for r in result.requirements]
        return state
```

### 4.4 C2 — Planning Layer（架构规划层，14 节点 + 1 处回退循环）

```text
knowledge_augment → pattern_recommend → pattern_confirm → tech_stack_select
→ component_decompose → cost_estimator → timeline_planner → skill_gap_analyzer
→ risk_quantifier → data_arch_design → api_planning → deployment_planning
→ self_check →(条件)→ assemble → END
             └→(self_check_passed=False)→ pattern_recommend（回退重规划）
```

| 节点 | 输入→输出 | 说明 |
|------|----------|------|
| `knowledge_augment` | analysis_result → knowledge_context | 调 RetrievalPipeline（query=项目名+架构设计+技术栈），无 LLM 链 |
| `pattern_recommend` | project/domain/req_count → architecture_patterns | LLM 推荐 2-3 模式 |
| `pattern_confirm` | architecture_patterns → selected_pattern | **纯逻辑**：取 max(match_score) 模式名；无候选回退"分层架构" |
| `tech_stack_select` | → tech_stack_choices | 维度：backend_framework/database_primary/cache/message_queue/frontend/testing/ci_cd/monitoring |
| `component_decompose` | requirements[:10] → component_decomposition | |
| `cost_estimator` | → node_outputs.cost_estimates | 3 种方案（low_cost/standard/high_availability） |
| `timeline_planner` | → node_outputs.timeline | 文本，无结构化 parser |
| `skill_gap_analyzer` | → node_outputs.skill_gaps | 无 stack 时跳过 |
| `risk_quantifier` | → node_outputs.risks[] | 概率×影响 |
| `data_arch_design` | → node_outputs.data_arch | 文本 |
| `api_planning` | → node_outputs.api_plan | 文本 |
| `deployment_planning` | → node_outputs.deployment_plan | 文本 |
| `self_check` | → node_outputs.self_check_passed + self_check_result | 条件路由关键 |
| `assemble` | 聚合 → planning_result | 同步，含 _build_mermaid 组件关系图 |

**PlanningState 关键字段**：`analysis_result, knowledge_context, architecture_patterns, selected_pattern, tech_stack_choices, component_decomposition, planning_result, node_outputs` + Orchestrator 注入 `evaluation_feedback`。

**output_models.py**：`ArchitecturePattern/PatternRecommendResult, TechStackItem/TechStackResult, DecomposedComponent/ComponentDecomposeResult, CostEstimateTier/CostEstimateResult, RiskItem/RiskQuantifyResult, SelfCheckResult`（9 个 Pydantic 模型）。

### 4.5 C3 — Generation Layer（方案生成层，8 节点 + Send 并行扇出）

```text
outline ──[条件: fan_out_sections]──→ [section_writer × n 并行] ──→ diagram
   └(无未写章节)→ diagram
diagram → code_scaffold → consistency → revision → assemble → export → END
```

| 节点 | 输入→输出 | 说明 |
|------|----------|------|
| `outline` | 选模板（电商→ecommerce.yaml，否则 default.yaml）→ outline | 同步，无 LLM；14 节或 3 节兜底 |
| `section_writer` | `_section_target` → 该节 section_contents | **Send Worker 并行**；流式 `gateway.stream_complete()` + EventBus 推送 generation.section/chunk |
| `diagram` | planning_result.component_diagram → mermaid_diagrams.architecture | 同步 |
| `code_scaffold` | → code_scaffold | 可编译代码框架 |
| `consistency` | section_contents → consistency_issues | "通过"则空 |
| `revision` | 有 issues 才执行 → section_contents["_revision_fix"] | |
| `assemble` | 聚合 → generation_result | 同步 |
| `export` | → export_formats{markdown,html,pdf(base64),docx(base64)} | 同步；PDF 优先 weasyprint 降级 fpdf2 |

**Send 扇出实现**：

```python
def fan_out_sections(state):
    # 为每个未写章节创建 Send("section_writer", {**state, "_section_target": section})
    # 全部写完则 Send("diagram", state)
    return [Send("section_writer", {**state, "_section_target": section})
            for section in state["outline"]
            if section.section_id not in state.get("section_contents", {})] \
           or [Send("diagram", state)]

# reducer: merge_contents 合并并行写入的 section_contents
```

**模板引擎（generation_layer/templates/engine.py）**：Jinja2 `FileSystemLoader`；三级模板（行业 `industry/{industry}.yaml` → 回退 `industry/default.yaml`；章节 `section/{name}.md`）。实际文件：`industry/{default,ecommerce}.yaml`、`section/{architecture,background}.md`。

### 4.6 C4 — Evaluation Layer（评测层，Send 并行 9 节点）

```text
[条件入口] fan_out_evaluators ──[Send]──→ 9 个评测节点并行 ──fan-in──→ scoring → END
```

**Send() 并行扇出（Block G 已实现）**：

```python
# _EVALUATOR_DIMS 映射:
#   coverage→prd_coverage, consistency, feasibility, arch_quality→architecture_quality,
#   security, cost_eval→cost, implementability, tech_advancement, legal→legal_compliance

def fan_out_evaluators(state):
    # 为每个未评估的维度创建 Send(node_name, state)；全部已评估则 Send("scoring")
```

| 节点 | 评分关注点 | 键 |
|------|-----------|-----|
| `PRDCoverageCheckNode` | PRD 需求覆盖率（requirements vs generation.content[:2000]） | prd_coverage |
| `ConsistencyEvalNode` | 架构/技术栈/组件内部矛盾 | consistency |
| `FeasibilityEvalNode` | 技术可行性 | feasibility |
| `ArchitectureQualityNode` | 可扩展/可维护/性能/安全/可测 | architecture_quality |
| `SecurityComplianceNode` | 认证授权/加密/日志审计/漏洞 | security |
| `CostEvalNode` | 成本合理性（tech_stack + len(components)） | cost |
| `ImplementabilityEvalNode` | 团队技能+实施周期（⚠️ 读 node_outputs 实际取不到，走默认值） | implementability |
| `TechAdvancementEvalNode` | 成熟度/活跃度/生态/创新 | tech_advancement |
| `LegalComplianceEvalNode` | GDPR/个保法/开源协议/监管 | legal_compliance |

**统一评分模式**：`ChatPromptTemplate | GatewayChatModel(task_type="evaluation") | PydanticOutputParser(ScoreResult)`；`ScoreResult={score=5.0, issues, verdict}`；异常时 score=5.0；写入 `dimension_scores[键]`。

**评分汇总（scoring.py，⚠️ 非显式加权公式）**：

```text
ScoringNode.run(state):
  1. 收集已有 dimension_scores（并行节点写入，reducer merge_scores 自动合并）
  2. 调 LLM（model="gpt-4o-mini"，SCORING_PROMPT）补全缺失维度
  3. 合并: 子节点评分优先 → LLM 补全 → 缺失默认 5.0
  4. ScoreCalibrator.calibrate(overall, merged) 校准
  5. 产出 EvaluationReportDetail(overall_score, dimension_scores, conclusion,
     p0_coverage, critical_issues, recommendations)
```

> **⚠️ 注意**：代码里没有真正的 10 维加权求和向量（`completeness` 维度无对应子节点，全靠 LLM 补）。

**评分校准（score_calibrator.py，⚠️ 仅实现 1 种）**：

```text
历史比对:  calibrated_overall = (overall + avg_prev_history_overall) / 2.0
平行评测（多模型取中位数）: 未实现（仅 docstring 占位）
history:  内存列表，不持久化
```

---

## 五、主编排层（Block D）

### 5.1 三层数据模型（app/orchestrator/state.py）

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
    task_id, prd_raw, prd_file_type, workspace_id, user_id, user_role, permissions
    tenant_context: TenantContext          # organization_id/workspace_id/knowledge_scope/settings
    knowledge_context                      # 块 B
    analysis_result, extracted_requirements, extracted_constraints   # 块 C1
    planning_result, component_decomposition, tech_stack_choices     # 块 C2
    generation_result, section_contents, export_formats              # 块 C3
    evaluation_report                      # 块 C4
    chat_response                          # 对话路径
    iteration_count, max_iterations, status(running/paused/complete/failed/clarification_needed),
    error_message, progress
    intent, intent_confidence, intent_sub  # 意图（NotRequired）
    # 运行时未声明字段（# type: ignore[typeddict-unknown-key] 访问）:
    #   _history_messages, retrieved_memories, compressed_context, _runtime

# 3. Runtime 层 — 每次请求注入，不参与 checkpoint 序列化
class OrchestratorRuntime:
    db_session, event_bus, llm_gateway, current_user_id, current_workspace_id, started_at
```

### 5.2 主编排图完整拓扑（app/orchestrator/main_graph.py）

```text
classify（入口，IntentClassifyNode，幂等）
    │  route_by_intent 条件路由
    ├─ chat → chat_node → save_session → END
    ├─ knowledge_qa → retrieve_node → save_session → END
    ├─ clarification → clarify_node → END
    └─ complex_generation → kg_retrieve → retrieve_memory
                              │
                              ▼
                         knowledge_retrieval（RetrievalPipeline hybrid）
                              │
                              ▼
                            analysis（AnalysisAdapter）progress=0.25
                              │  needs_review 条件路由
                     ┌────────┴────────┐
                     ▼                 ▼
             analysis_human_review   planning（PlanningAdapter）progress=0.50
                     │                 │  needs_review 条件路由
                     └────────────────┼──────────────┐
                                      ▼              ▼
                              planning_human_review generation（GenerationAdapter）progress=0.75
                                      │              │
                                      └──────────────▼
                                                  evaluation（EvaluationAdapter）progress=0.90
                                                      │  IterationDecider 条件路由
                              ┌───────────────────────┼─────────────┐
                              ▼                       ▼             ▼
                    final_assembly(≥85/max迭代)    planning(重规划)  generation(重生成)
                              │                       analysis_human_review(<70+严重问题)
                              ▼
                         compress_memory
                              │
                              ▼
                         save_session
                              │
                              ▼
                            END
```

**节点清单（15 个，全部 trace_node 包装）**：`classify / chat_node / retrieve_node / clarify_node / knowledge_retrieval / analysis / analysis_human_review / planning / planning_human_review / generation / evaluation / final_assembly / retrieve_memory / compress_memory / save_session`。

**编译**：

```python
build_orchestrator_graph(analysis_graph, planning_graph, generation_graph, evaluation_graph,
    retrieval_pipeline=None, session_service=None, context_compressor=None,
    memory_retriever=None, llm_gateway=None) -> StateGraph  # 未编译

build_and_compile(..., use_checkpointer=False, checkpointer=None, config=None, ...) -> StateGraph
    # checkpointer 优先级: 显式 checkpointer > use_checkpointer=True 时 MemorySaver() > 无

create_postgres_checkpointer(db_url=None):
    # Settings().DATABASE_URL 去 +asyncpg → PostgresSaver.from_conn_string(sync_url) → setup()
create_memory_checkpointer():  # MemorySaver()
```

**依赖注入（app/api/deps.py）**：`get_orchestrator()` 懒加载——首次从各 Layer 的 `agent_graph` 导入 4 个编译图，构造 `ContextCompressor()` / `MemoryRetriever()` / `SessionHistoryService()`，`build_and_compile(checkpointer=_checkpointer_instance, llm_gateway=gateway, ...)` 后缓存复用。

### 5.3 意图分类（IntentClassifier）

```text
IntentType: chat / knowledge_qa / complex_generation / clarification / document_analysis

classify(user_input, session_history=None):
  1. 规则层（快路径）: 命中且 confidence >= 0.8 直接返回
  2. LLM 层: _llm_classify（temperature=0.1, max_tokens=200, 带最近 3 条会话历史）
             若 llm confidence > rule confidence 则用 LLM 结果
  3. 兜底: COMPLEX_GENERATION, confidence=0.5

规则优先级:
  GENERATION_PATTERNS（生成/创建/编写/设计/TSD/PRD）→ complex_generation, 0.85
  DOCUMENT_ANALYSIS_PATTERNS（分析这个/总结文档）→ document_analysis, 0.85
  KNOWLEDGE_PATTERNS（是什么/如何）≥2 个 → knowledge_qa, 0.9；==1 个 → 0.7
  CHAT_PATTERNS（你好/hello）→ chat, 0.8
  短查询(<8字) → knowledge_qa, 0.6
```

**图内 classify 节点幂等**（app/orchestrator/nodes/intent_classify.py）：

```python
INTENT_ROUTE_MAP = {
    "chat": "chat_node",
    "knowledge_qa": "retrieve_node",
    "complex_generation": "kg_retrieve",
    "clarification": "clarify_node",
    # document_analysis 不在映射内，落到默认 chat_node（interact 层已处理）
}
route_by_intent(state): return INTENT_ROUTE_MAP.get(state.get("intent", "chat"), "chat_node")
```

### 5.4 迭代决策（IterationDecider）

```python
def run(state) -> str:
    # iteration_count 已在 EvaluationAdapter 中递增
    if iteration_count >= max_iterations:                 return "final_assembly"   # accept
    if evaluation_report is None:                         return "generation"       # regenerate
    if overall_score >= 85:                               return "final_assembly"   # accept
    if overall_score >= 70:
        if dimension_scores["consistency"] < 70:          return "generation"       # regenerate
        if dimension_scores["feasibility"] < 70:          return "planning"         # replan
        return "final_assembly"
    # < 70
    if critical_issues:                                   return "analysis_human_review"  # human
    return "planning"                                                              # replan

ROUTE_MAP = {"accept":"final_assembly", "replan":"planning",
             "regenerate":"generation", "human_intervention":"analysis_human_review"}
```

> **⚠️ 注意**：85/70 阈值为硬编码，未读 `OrchestratorConfig.evaluation_pass_threshold/replan_threshold`（config 在 build_and_compile 接受但未使用）。

### 5.5 人工审核（HumanReviewNode）

```python
run(state)（同步方法）:
  review_context = {stage, task_id, description, data}
    # analysis: analysis_result + requirements/constraints 数量
    # planning: planning_result + components/tech_choices 数量
  feedback = interrupt(review_context)          # ⚠️ 图执行暂停，state 写入 checkpointer
  if feedback.decision == "needs_changes":
      state["status"] = "paused"; 记录 error_message
  else:
      state["status"] = "running"
```

**恢复**：`POST /api/v1/review/{task_id}/{stage}` → TaskManager.resolve_review → `Command(resume={"decision","comment"})` 驱动 `astream` 从 checkpointer 恢复。

### 5.6 条件路由（needs_review）

```python
needs_review(state) -> str:
    tenant_context.settings.get("auto_approve") 为 True 或 user_role == "admin"
        → "skip_review"
    否则 → "review_needed"
```

### 5.7 Adapter 模式（状态映射）

统一模式：`__init__(graph: StateGraph)` 持有编译后的 Layer 图；`async run(state) -> OrchestratorState` 执行「提取输入 → `graph.ainvoke(input)` → 写回 state + 更新 progress」。

| Adapter | 输入 | 输出写回 | progress |
|---------|------|---------|----------|
| `AnalysisAdapter` | prd_raw + system_prompt(租户) + knowledge_context | analysis_result / extracted_requirements / extracted_constraints | 0.25 |
| `PlanningAdapter` | analysis_result + knowledge_context + evaluation_feedback | planning_result / component_decomposition / tech_stack_choices | 0.50 |
| `GenerationAdapter` | planning_result + analysis_result + section_contents + export_formats + task_id(SSE) + evaluation_feedback + system_prompt + claims_constraints | generation_result / section_contents / export_formats | 0.75 |
| `EvaluationAdapter` | analysis_result + planning_result + generation_result | evaluation_report / iteration_count+=1 | 0.90 |

### 5.8 主编排各节点职责

| 节点 | 职责 |
|------|------|
| `KnowledgeRetrievalNode` | pipeline.retrieve(query=prd_raw[:500], mode="hybrid", top_k=10)；空 PRD 跳过；失败降级 None；DecisionRecorder.start_trace；progress=0.10 |
| `FinalAssemblyNode` | status=complete、progress=1.0、DecisionRecorder.end_trace、integration_hub.notify("task.completed") |
| `ChatNode` | gateway.stream_complete(task_type="chat")，SSE: chat.status→chat.chunk→chat.done |
| `KnowledgeQANode` | pipeline.retrieve(top_k=5) → global_summary+results 拼 RAG prompt → stream_complete；SSE: qna.status→qna.chunk→qna.done |
| `ClarifyNode` | 不调 LLM；SSE: chat.clarify；status=clarification_needed |
| `RetrieveMemoryNode` | MemoryRetriever.retrieve(query=prd_raw[:500], strategy="hybrid", top_k=10) → retrieved_memories |
| `CompressMemoryNode` | ContextCompressor.compress(_history_messages) → compressed_context |
| `SaveSessionNode` | 提取 chat_response/generation_result.summary + overall_score；发布 task.saved 事件 |

> **⚠️ 已知问题**：`RuntimeInjector` 未接入 `build_orchestrator_graph`（图中无节点调用 `inject`），`_runtime` 从未注入 → `chat_node`/`retrieve_node`/`clarify_node` 实际拿到的 `event_bus=None`（SSE 副作用在当前图运行路径上不生效，走全局 gateway）。详见第二十一章。

---

## 六、企业级功能层（Block E）

### 6.1 统一交互入口（POST /api/v1/interact）

> Block E B1 整改后，`/chat`、`/generate`、`/qna/stream`、`/generate/stream`、`/csv-import`、`/search-fallback` 均已删除，统一收敛到 `/api/v1/interact`。交互入口是唯一意图判定来源（消除双实现）。

```text
POST /api/v1/interact  Body: { message, session_id, workspace_id, stream, doc_id, url, generate, prd_type }

_interact():
  1. _classify_intent(req):
       - 请求携带 url 或 doc_id → 强信号判定 document_analysis（confidence 0.9）
       - 否则 → IntentClassifier.classify(message)
  2. stream=true → _route_stream（SSE）
  3. 同步 → _route_sync:
       document_analysis     → 文档分析（doc_id/url，同步摘要 或 generate=true 建生成任务）
       complex_generation    → task_manager.create_task() → 返回 task_id
       chat/knowledge_qa/clarification → _graph_sync:
           make_initial_state + 预写 intent（图内 classify 幂等跳过）→ orchestrator.ainvoke
           → 图异常时降级直接 gateway.complete 回答
```

**流式模式**（_route_stream）：返回 `text/event-stream`，复用 `app/streaming/sse.py` 工具 + EventBus，具体事件见第十四章。

### 6.2 文档管理（app/document_management/）

```text
上传流程（service.upload）:
  1. 类型校验（.md/.pdf/.docx/.txt/.csv/.tsv/.png/.jpg/.jpeg）
  2. 大小校验（≤ 50MB）
  3. SHA-256 去重（get_by_hash，重复返回 deduplicated=True）
  4. 存 MinIO（路径 prd-docs/{workspace_id}/{yyyy}/{mm}/{hash}{ext}）
  5. 写 DB（uploaded_documents 表，processing_status=pending）
  6. 若 is_indexable(filename) → _trigger_kg_index:
       Celery index_document_to_kg.delay(document_id)  # Celery 不可用降级跳过
```

**其他能力**：

| 能力 | 实现 |
|------|------|
| 读取正文 | `get_document_content` 返回原始字节 + 文件名（供 multi_format_loader 提取真实内容） |
| 删除 | MinIO 删 + DB 软删 |
| 预览 | `_preview_docx` / `_preview_pdf`（复用 extract_text）/ csv 前 20 行 / 图片占位；MAX_PREVIEW_CHARS=5000 |
| 搜索 | `to_tsvector('simple', title+description+original_filename)` + `ts_rank`；语义向量为 docstring 占位未实现 |
| 统计 | `get_stats`：总量/大小/按类型/按状态 |
| 重索引 | `reindex` |

**uploaded_documents 表字段**：`workspace_id, user_id, original_filename, storage_path, file_size, file_type, mime_type, file_hash, title, description, page_count, word_count, source_url, processing_status(pending/processing/indexed/failed), processing_error, indexed_at, entity_count, relation_count, session_id, task_id, tags, is_deleted, deleted_at`。

### 6.3 URL 文档分析（SSRF 防护 + 入库）

```text
url_security.validate_url(url):
  - 协议白名单（http/https）、长度 ≤ 4096
  - localhost 名直接拦截
  - IP 字面量: is_private/loopback/link_local/reserved/multicast/unspecified 拦截
  - 域名: socket.getaddrinfo 后逐个检查所有解析 IP（防域名指向内网）
  - DNS 阻塞操作经 asyncio.to_thread 包裹

UrlDocumentService:
  fetch_content(url):  SSRF 校验 → WebLoader.fetch → 附加 validated_url
  ingest(db, ws_id, user_id, url, ...): 校验 → 抓取（≤20MB）→ docs.upload(.md)
      → repository.update 标记 file_type="url" + source_url 溯源
```

**interact 中 URL 的三种用途**：
1. `url`（无 generate）→ 抓取 → 入库 → `_analyze_document`（LLM 同步摘要）
2. `url + generate=true` → 抓取 → 以抓取文本为 PRD 创建 complex_generation 任务（一键生成 TSD）
3. `doc_id` → `_load_document_text`（get_document_content + extract_text 提取真实正文）→ 分析

### 6.4 Web 资源索引（app/web_indexing/）

```text
WebLoader.fetch(url):      httpx GET（UA Prd2TsdBot/1.0，follow_redirects）
    返回 {url,title,content(Markdown),text_content,html,content_type,status_code,error}
    正文提取: 正则匹配 article/main/div.content/body（无 Readability 依赖），截断 10000 字符
    _html_to_markdown_simple: h1-h6/p/li/strong/b/em/i/a/code/pre

WebCrawler.crawl(start_url): BFS + visited + queue；尊重 robots.txt Disallow；
    同域 <a href> 去 fragment 入队；max_pages=50

WebSyncScheduler: 内存 dict 跟踪 {url: {etag, last_modified, content_hash}}
    sync(url): If-None-Match/If-Modified-Since 条件请求，304 → 未变更；否则 sha256 内容哈希对比
```

### 6.5 会话历史管理（app/session_history/）

```text
创建会话:  SessionRepository.create_session() → 自动生成 thread_id=uuid4()
消息添加:  add_message → turn_index = max(turn_index)+1，更新 message_count/last_message_at
会话搜索:  PostgreSQL FTS: plainto_tsquery("simple") + to_tsvector("simple", content) + ts_rank
消息搜索:  /sessions/search/messages 同理
会话导出:  markdown（带角色 emoji）/ json
摘要标题:  SessionSummarizer.generate_title（10 字内，失败截前 50 字）/
           generate_summary（最近 10 条消息，50 字内）
老化清理:  SessionCleanupPolicy.RETENTION_DAYS = {"free":30, "pro":180, "enterprise":0(不限)}
          未知套餐默认 30 天；last_message_at < cutoff 软删

SessionOut 含 LangGraph 断点字段: thread_id / checkpoint_ts / current_node / interrupt_stage
```

**上下文压缩（ContextCompressor）**：

```text
三级压缩策略按优先级 ["summarize", "rolling", "truncate"]:
  默认 max_tokens=128_000, reserve_for_latest=32_000（保护区）
  ① summarize: 最旧消息 LLM 摘要（task_type="memory_compress"）→ [system: [历史摘要]...]
  ② rolling:   滑动窗口丢弃最旧
  ③ truncate:  二分截断最旧文本
  终极兜底:    仅保留保护区
  token 估算同 Compressor: 中文 1.5 / 英文 0.25
```

**记忆检索（MemoryRetriever）**：

```text
retrieve(query, messages, strategy, top_k=10) -> [MemoryItem]
  4 策略权重:
    hybrid:  recency 0.3 + relevance 0.4 + importance 0.3
    recency:  指数衰减 exp(-hours_ago/24)（24h 半衰期；⚠️ 实际 timestamp 用 now，recency 全近 1.0）
    relevance: 关键词重叠率（vector_store 传入但未使用，纯词重叠）
    importance: LLM 打分（0-1，无 gateway 默认 0.5）
```

### 6.6 SSE 流式推送（EventBus + sse.py）

```text
EventBus（asyncio.Queue 内存 Pub/Sub）:
  _channels: {channel: set[Queue]}, _queue_maxsize=128
  publish(channel, event): put_nowait 非阻塞，队列满静默丢弃
  subscribe(channel) -> Queue / unsubscribe(channel, queue)

SseEvent: {type, payload, timestamp}
  to_sse_line() -> "data: {json}\n\n"（ensure_ascii=False）

sse.py 工具:
  KEEPALIVE_INTERVAL=30
  subscribe_task_events(channel, *initial_events): 初始事件 → 订阅 → wait_for(30s) 超时发 keepalive
      → done/error 时 break → finally unsubscribe
  sse_response(generator): StreamingResponse + headers(Cache-Control no-cache / X-Accel-Buffering no)
```

**事件类型全集（EVENT_TYPES 已登记 + 代码实际出现）**：

| 类型 | 触发 | 备注 |
|------|------|------|
| `task.created` / `task.progress` / `task.log` / `task.status` | TaskManager 生命周期 | ✅ 已登记 |
| `task.review_required` / `task.review_resolved` | 审核 | ✅ 已登记 |
| `task.snapshot` | SSE 初始快照 | ✅ 已登记 |
| `generation.chunk` / `generation.section` | SectionWriter 流式 | ✅ 已登记 |
| `qna.chunk` / `qna.status` | 知识问答 | ✅ 已登记 |
| `keepalive` / `done` / `error` | 心跳/完成/错误 | ✅ 已登记 |
| `chat.status` / `chat.chunk` / `chat.done` / `chat.clarify` | ChatNode | ⚠️ 代码出现但未登记 EVENT_TYPES |
| `task.saved` | SaveSessionNode | ⚠️ 代码出现但未登记 EVENT_TYPES |

### 6.7 批量处理与定时任务（Celery）

```text
BEAT_SCHEDULE（app/batch/scheduler.py）:
  refresh-knowledge-graph  → prd2tsd.batch.tasks.refresh_knowledge_graph  （24h）
  cleanup-expired-sessions → prd2tsd.batch.tasks.cleanup_expired_sessions （1h）
  sync-web-resources       → prd2tsd.batch.tasks.sync_web_resources       （2h）

Celery 任务（app/batch/tasks.py，均 max_retries=3）:
  refresh_knowledge_graph:    KnowledgeGraphBuilder.get_stats()（retry 60s）
  cleanup_expired_sessions:   SessionRepository + SessionCleanupPolicy（retry 30s）
  sync_web_resources:         WebIndexer().sync_all()（retry 120s）⚠️ WebIndexer 类不存在（见 21）
  index_document_to_kg(doc_id): 查 UploadedDocument → 下载 → build_from_bytes → 更新 processing_status

BatchTaskService: 批量重索引/重新生成（内存存储，重启丢失，注明需迁 PG）
手动触发: POST /api/v1/batch/scheduler/trigger/{task_name} → celery_app.send_task 真正触发
```

### 6.8 Webhook 通知（app/integrations/webhook.py）

```text
WebhookSender.send(url, event, payload): body {event, timestamp, data: payload}
    可选 HMAC-SHA256 签名放 X-Webhook-Signature；httpx 超时 15s；UA Prd2Tsd-Webhook/1.0
send_task_completed(url, task_id, workspace_id, summary): event="task.completed"

IntegrationHub（全局单例 integration_hub）:
  _webhooks: {workspace_id: {event: url}}
  register_webhook / unregister_webhook / list_webhooks
  notify(event, payload, sender=None): 遍历所有注册该事件的 workspace 发送

触发点: FinalAssemblyNode 任务完成 → integration_hub.notify("task.completed")
API:   POST/DELETE/GET /api/v1/integrations/webhooks + POST /integrations/webhooks/test
```

### 6.9 文档上传 → 入图链路

```text
POST /api/v1/documents/upload（multipart 文件）
  │
  ① 类型校验（ALLOWED_EXTENSIONS）
  ② 大小校验（≤ 50MB）
  ③ SHA-256 去重（get_by_hash）
  │    ├─ 重复 → 返回 {document, deduplicated: True}（不重复入库）
  │    └─ 新文档 ↓
  ④ 存 MinIO（prd-docs/{workspace_id}/{yyyy}/{mm}/{sha256}{ext}）
  ⑤ 写 uploaded_documents（processing_status=pending, file_hash, storage_path, ...）
  ⑥ 若 is_indexable(filename):
       celery index_document_to_kg.delay(document_id)（Celery 不可用降级跳过）
        │
        └─ 异步执行（见第三章 3.12 构建链路）:
           下载字节 → extract_text → build_from_text → 双写 Neo4j+PGVector
           → 更新 processing_status(processing→indexed) + entity_count/relation_count

查询消费:
  - 全文检索: GET /documents?q=（FTS title+description+filename）
  - 知识检索: 入图成功后，实体/向量进入 RetrievalPipeline 可检索
  - 文档分析: POST /interact {doc_id} → get_document_content + extract_text
```

---

## 七、生产级加固层（Block F）

### 7.1 ⚠️ 工具系统（已废弃）

> **版本变更**：`app/agents/tools/`（ToolRegistry 生态）**已废弃**。`main.py` lifespan 明确注释：
> "Agent 工具已废弃 — ToolRegistry 零调用，待 LangChain @tool + ToolNode 替代"，工具注册代码已注释。
> 当前仅保留 `agents/{base,context,registry,result}.py` 与 `tools/{system_tools,llm_tool,knowledge,document,code}.py` 空壳文件，**不再是活跃能力**。

### 7.2 护栏系统（7 个可插拔护栏）

```text
GuardrailManager（app/llm_gateway/guardrails/manager.py）:
  register(guard): 按 guard.stage 分类到 _pre_guards / _post_guards
  check_input(text, context):  依次执行前置护栏，blocked 则 break
  check_output(text, context): 依次执行后置护栏，blocked 且 severity=="critical" 则 break

pre_llm 阶段（Gateway.complete 步骤 0）:
  PromptInjectionGuardrail   检测提示注入（ignore previous instructions / DAN / system: 等）
  PIIDetectorGuardrail       检测并脱敏 PII（邮箱/手机/身份证号）
  TimeoutGuardrail           检查 CircuitBreaker 状态

post_llm 阶段（步骤 7）:
  ContentSafetyGuardrail     检测不安全内容
  OutputValidatorGuardrail   校验输出格式（response_format 时校验 JSON）
  EmptyResponseGuardrail     检测空响应
  RetryDecisionGuardrail     汇总决定 retry/fallback/continue

GuardrailResult { passed, blocked, reason, severity, masked_text, metadata }
护栏拦截/限流/全失败路径均会记录 LLM_CALL_TOTAL（避免指标低估）
```

### 7.3 熔断器（Circuit Breaker）

```text
Provider 级熔断: name="provider:{deepseek|openai|anthropic|cohere}"
  failure_threshold=3, recovery_timeout=30s, half_open_max_requests=1

Gateway 中的使用:
  complete():  resolve_model → 若当前 Provider 已熔断（cb.is_available=False）则走 Failover 链
  stream_complete(): 遍历 failover.get_target()，熔断的 target 直接 continue 跳过
```

### 7.4 Provider Failover 链

```text
FailoverManager:
  configure("llm", [deepseek-chat(P0), gpt-4o-mini(P1)])
  configure("embedding", [text-embedding-3-small(P0)])
  get_target(model_type): 跳过不健康 target，health_check_interval=60s（_ping 最小请求探测）
  record_failure(model_type, provider): 标记 unhealthy，重置 index
  AllProvidersUnavailableError: 全不可用时抛出
```

### 7.5 语义缓存 / 速率限制 / 预算控制

```text
SemanticCache:  make_key = SHA-256("{task_type}::{prompt}")
                TTL 1h, max_size 1000（满时删最旧）；命中返回 cached=True cost=0
RateLimiter:    RPM(默认 60) + TPM(默认 100000) 滑动窗口 60s，按 workspace；set_limit 自定义
BudgetController: 月预算(默认 $100)，check_and_record；超 90% → should_downgrade
                → gateway 自动降级: gpt-4o-mini→openai / deepseek-chat→deepseek
```

### 7.6 记忆增强（MemoryRetriever + ContextCompressor）

> 已在第六章 6.5 详述。MemoryRetriever 四策略（hybrid 权重 recency 0.3 + relevance 0.4 + importance 0.3）；ContextCompressor 三级压缩（summarize → rolling → truncate），保留 32000 token 保护区。

### 7.7 Prompt 版本管理（app/core/prompt_registry/）

```text
PromptRegistry:  版本化存储（PromptVersion: id/name/version/content/hash/author/changelog/is_active/tags）
                 get/upsert/delete、按版本回滚、Diff 对比、A/B 测试配置（ABTestConfig）
Storage:         内存实现（registry.py 内）
```

### 7.8 Agent 行为回放（app/observability/replay/）

```text
DecisionRecorder:
  start_trace(task_id)     → 建 TraceTree
  record_decision(...)     → DecisionRecord（LLM 输入/输出、工具调用、state diff、耗时、token）
                             追加到 trace.nodes + edges，异步生成决策摘要
  end_trace(task_id)       → 保存完整 TraceTree（总耗时）

ReplayStorage:  内存 dict（records + traces）
ReplayPlayer:   get_trace / replay_step(task_id, step_index) / export_replay(markdown)
DecisionAnalyzer: analyze_trace(trace) → 汇总分析

触发点: KnowledgeRetrievalNode.start_trace + FinalAssemblyNode.end_trace
       （⚠️ 仅两处调用，中间节点未调用 record_decision，实际记录粒度有限）
```

### 7.9 数据脱敏 / 审计日志

> 已在第二章 2.6 详述。DataClassifier L1-L4 分级、DataMaskingEngine 正则替换 `[MASKED_XXX]`、AuditLogger 哈希链审计（verify_hash_chain 校验）。

### 7.10 结构化输出（LangChain PydanticOutputParser）

```text
app/llm_gateway/output_parser.py:
  PydanticOutputParser(pydantic_model): get_response_format()（JSON Schema）/
      get_format_instruction() / parse(text)（失败抛 OutputParseError）
app/llm_gateway/prompt_builder.py: PromptBuilder(system_prompt).build(...)
app/llm_gateway/pricing.py: estimate_cost(model, input_tokens, output_tokens)

Agent 节点统一模式: ChatPromptTemplate | GatewayChatModel | PydanticOutputParser
  → 一次调用完成: Prompt 构建 → LLM 调用 → JSON 解析 → Pydantic 验证
```

---

## 八、评测与观测层（WP1/WP2）

> 本节对应 `docs/plan-observability-eval-cleanup.md` 的 WP1（观测）与 WP2（评测），已于 2026-08-13 实施完成。

### 8.1 观测：OpenTelemetry 全链路追踪（app/observability/tracing.py）

```text
tracer 全局实例（_init_tracer）:
  Resource(service.name=OTEL_SERVICE_NAME, service.version=0.1.0)
  OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT) + BatchSpanProcessor → Jaeger
  OTLP 未配置时降级内存 SpanProcessor

HTTP 根 Span:  http_tracing_middleware（@app.middleware("http")）
  span name: "http.{method} {path}"，kind=SERVER
  attributes: http.method / http.path / http.user_id / http.status_code
  异常 record_exception；同时记录 HTTP_REQUESTS_TOTAL + HTTP_REQUEST_DURATION 指标

节点 Span:  trace_node(node_name) 统一包装器
  根据 inspect.iscoroutinefunction 自动选 wrap_node（同步）或 wrap_async_node（异步）
  span name: "node.{node_name}"，kind=INTERNAL
  attributes: task_id / workspace_id / layer / iteration / duration_ms
  已应用到: 主编排 15 节点 + Analysis 11 + Planning 14 + Generation 8 + Evaluation 9（条件入口函数不包装）

LLM Span:  gateway.complete → "gateway.complete.{task_type}"（kind=CLIENT）
           gateway.stream_complete → "gateway.stream_complete.{task_type}"
  attributes: task_type / workspace_id / layer / node / model / tokens / cost

完整 trace 树:  http.* → node.* → gateway.complete.*（Jaeger UI 可查，http://localhost:16686）
```

### 8.2 观测：Prometheus 指标（app/observability/metrics.py）

| 指标 | 类型 | labels | 说明 |
|------|------|--------|------|
| `llm_calls_total` | Counter | model/layer/node | LLM 调用总数（含缓存命中/拦截/失败路径） |
| `llm_latency_seconds` | Histogram | model | buckets [0.1..30] |
| `llm_tokens_total` | Counter | model/type(input/output) | Token 消耗 |
| `llm_cost_total_usd` | Counter | model | 累计成本 |
| `http_requests_total` | Counter | method/path/status | HTTP 请求总数 |
| `http_request_duration_seconds` | Histogram | method/path | buckets [0.01..10] |
| `tasks_total` | Counter | status(created/completed/failed) | 任务总数 |
| `tasks_duration_seconds` | Histogram | - | buckets [10..1800] |
| `sessions_total` | Counter | workspace_id | 会话总数 |
| `documents_total` | Gauge | workspace_id/file_type | 文档总数 |
| `documents_storage_bytes` | Gauge | workspace_id | 文档存储总量 |

```text
track_llm_call(model, layer, node) 上下文管理器:
  with track_llm_call(...) as token_info:
      调用方在块内设 token_info["input_tokens"] / ["output_tokens"]
  finally: 记录 llm_calls_total / llm_latency_seconds / llm_tokens_total

接入点:  Gateway.complete / stream_complete（成功、缓存命中、护栏拦截、限流、全失败路径均计数）
        TaskManager.create_task（created）/ _execute_task 成功（completed）/ 失败（failed）
        + TASKS_DURATION.observe

暴露:  GET /api/v1/metrics → metrics_app（prometheus_client.generate_latest）
部署:  Prometheus(:9090) + Grafana(:3000, provisioning + dashboards，storage/grafana/)
```

### 8.3 评测：RAG 评测（app/evaluation/rag/，基于 ragas 0.4.3）

```text
依赖: ragas==0.4.3（唯一精确锁版）
  _compat.py: 兼容 shim——langchain-community>=0.4 拆分 vertexai，
              ragas 0.4.x 顶层导入 ChatVertexAI 会报错 → import ragas 前向 sys.modules 注入占位模块

数据模型: RagSample{id,query,reference_answer,reference_contexts,source_file,expected_mode}
         RagQueryScore{context_precision, context_recall, faithfulness,
                       answer_relevancy, retrieved_count, reflection_rounds, total_tokens}
         RagEvalSummary / RagEvalReport

RagEvaluator:
  L1 指标 = context_precision / context_recall（检索质量）
  L2 指标 = faithfulness / answer_relevancy（回答质量，基于 ragas evaluate）
  retrieve_and_answer:  pipeline.retrieve(mode=expected_mode, top_k=config.top_k)
                        → 严格基于上下文回答 prompt（temperature=0.2）
  反思 A/B: evaluate_ab_reflection() 分别以 reflection=false/true（max_reflection_rounds 0/2）
            跑两组完整评测 → reflection_off / reflection_on / diff
  judge LLM / embedding 复用项目 judge / embedding 配置

CLI: scripts/run_rag_eval.py（--dataset/--variant/--ab-reflection）
数据集: tests/eval/datasets/rag_qa.json（12 条）
```

### 8.4 评测：Agent 评测（app/evaluation/agent/）

```text
数据模型: AgentTask{id,task,prd_input,expected_key_points,rubric,expected_max_iterations}
         AgentTaskScore{completed, iterations, human_review_required, duration_s,
                        judge_scores, judge_text}
         AgentEvalReport{completion_rate, avg_iterations, human_review_rate,
                         avg_judge_score, tasks, config}

AgentEvaluator:
  L3 过程指标: 完成率（status=="complete"）、迭代轮数（iteration_count）、
               人工介入率（needs_review）、耗时
  L4 结果质量: judge_result() 按 task.rubric 用 gateway.complete（temperature=0）
               JSON 打分 {"scores": {...}, "comments": {...}}
  _default_runner: 通过主编排图 get_orchestrator().astream 跑真实任务

CLI: scripts/run_agent_eval.py
数据集: tests/eval/datasets/agent_tasks.json（4 条）
```

### 8.5 评测运行链路

```text
run_rag_eval.py:
  load_rag_dataset → RagEvaluator.evaluate（逐 sample: retrieve_and_answer → ragas evaluate）
  → 汇总 RagEvalSummary → 写报告（tests/eval/reports/，.gitignore 忽略）

run_agent_eval.py:
  load_agent_dataset → AgentEvaluator.evaluate（逐 task: 跑主编排图 → L3/L4 打分）
  → 汇总 AgentEvalReport → 写报告

用途: 反哺优化——RAG 检索参数（top_k/reflection）、Agent 流程（迭代/审核）的 A/B 对比
```

### 8.6 可追踪链路（OpenTelemetry 全链路追踪 + Prometheus 指标链路）

> 本节回答"一次请求产生的追踪数据如何贯穿全系统，最终在 Jaeger / Prometheus / Grafana 呈现"。

#### 8.6.1 追踪链路：span 的生成与传播

```text
一次请求的 trace 树（同步路径 chat / knowledge_qa / interact）：

  http.POST /api/v1/interact          (SERVER)  ← 根 span，生成 trace_id/span_id
    └─ node.classify                   (INTERNAL)
        └─ node.chat_node             (INTERNAL)
            └─ gateway.complete.chat   (CLIENT)

  或 complex_generation 任务（异步路径）：
  http.POST /api/v1/interact          (SERVER)  ← 返回 task_id 后根 span 结束
    └─ [任务后台协程：继承创建时的 OTel context]
        └─ node.classify ... node.knowledge_retrieval
            └─ node.analysis
                └─ node.requirement
                    └─ gateway.complete.analysis  (CLIENT)
```

**span 逐层生成与传播**：

```text
① HTTP 根 span（app/main.py 注册的 http_tracing_middleware）
   - span name: "http.{method} {path}"，kind=SERVER
   - 由 OTel SDK 生成 trace_id / span_id，写入 contextvars
   - attributes: http.method / http.path / http.user_id / http.status_code
   - 异常 → record_exception；同时记录 http_requests_total / http_request_duration_seconds

② 节点 span（trace_node 包装器，覆盖主编排 15 节点 + 各 Layer 全部节点）
   - span name: "node.{node_name}"，kind=INTERNAL
   - 因与 HTTP 处理在同一 OTel context 中执行 → 自动成为 http span 的子级
   - attributes: task_id / workspace_id / layer / iteration / duration_ms
   - 异常 → record_exception + StatusCode.ERROR

③ LLM span（gateway.complete / stream_complete 内部）
   - span name: "gateway.complete.{task_type}" 或 "gateway.stream_complete.{task_type}"，kind=CLIENT
   - 在调用它的节点 span 上下文中创建 → 成为节点 span 的子级
   - attributes: task_type / workspace_id / layer / node / model /
                input_tokens / output_tokens / cost
     （stream_complete 另含 streaming / provider / failover_attempt）

④ span 导出
   - BatchSpanProcessor → OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT，
     默认 http://localhost:4317，OTLP gRPC) → Jaeger
   - OTLP 未配置 → 降级内存 SpanProcessor（不导出）

⑤ 查看
   - Jaeger UI（http://localhost:16686）
   - 按 service=prd2tsd + tag task_id=<task_id> 过滤 → 单次任务完整 trace 树
   - 按 http.user_id 过滤 → 单个用户请求链路
```

> **⚠️ 异步任务的 trace 特性**：`complex_generation` 经 `task_manager.create_task` →
> `asyncio.create_task(_execute_task)`，Python 会**复制当前 contextvars（含 OTel current span）**
> 到新协程，所以后台任务继承创建时的 span 上下文；但 HTTP 响应已提前返回（根 span 已结束），
> 后台任务的 node/gateway span 会挂在已结束的 http span 下（时间超父）或形成独立 trace。
> **因此按 task_id 检索最可靠**（所有 node span 均带 task_id attribute）。

#### 8.6.2 指标链路：埋点 → 暴露 → 采集 → 展示

```text
[埋点]                              [暴露]              [采集]               [展示]
metrics.py / 业务代码  →  GET /api/v1/metrics  →  Prometheus(:9090)  →  Grafana(:3000)
                           (generate_latest)     scrape 15s 间隔        provisioning + dashboards
```

**① 埋点（app/observability/metrics.py）**：

| 指标 | 类型 | 埋点位置 |
|------|------|---------|
| `llm_calls_total` | Counter | `track_llm_call` 上下文管理器（gateway complete/stream_complete 的 成功/缓存命中/护栏拦截/限流/失败 全路径） |
| `llm_latency_seconds` | Histogram | 同上（finally 计时） |
| `llm_tokens_total` | Counter | 同上（token_info.input/output_tokens） |
| `llm_cost_total_usd` | Counter | gateway 成本记录处 |
| `http_requests_total` / `http_request_duration_seconds` | Counter / Histogram | http_tracing_middleware |
| `tasks_total` / `tasks_duration_seconds` | Counter / Histogram | TaskManager create_task / _execute_task |
| `sessions_total` | Counter | 会话创建（待接线） |
| `documents_total` / `documents_storage_bytes` | Gauge | 文档统计（待接线） |

**② 暴露**：`GET /api/v1/metrics` → `metrics_app`（`prometheus_client.generate_latest()`，CONTENT_TYPE_LATEST）。

**③ 采集**（prometheus.yml）：

```yaml
scrape_configs:
  - job_name: "prd2tsd-api"
    static_configs:
      - targets: ["api:8000"]
    metrics_path: "/api/v1/metrics"
```

**④ 展示**（Grafana）：`storage/grafana/provisioning/datasources/prometheus.yml`（数据源）+ `dashboards/llm-metrics.json`（LLM 调用/任务指标面板）。

**完整可观测闭环**：HTTP/节点/LLM 全链路 span（Jaeger 查因果） + 指标（Prometheus/Grafana 查量级与趋势） + SSE 事件（前端实时进度）。

---

## 九、主线任务全链路逐节点详解

> 以下是一次 "complex_generation" 任务的完整执行链路（异步任务路径）。

### Step 0: 系统初始化（FastAPI lifespan）

```text
lifespan(app):
  1. setup_logger + init_connections() + connection_manager.startup()
     (PostgreSQL/Redis/MinIO/Neo4j 连接器启动)
  2. task_manager.set_event_bus(event_bus)          # EventBus 注入 TaskManager
  3. create_postgres_checkpointer() → set_checkpointer()
     失败则降级 create_memory_checkpointer()（MemorySaver 开发模式）
  4. OpenTelemetry tracer 初始化（OTEL_SERVICE_NAME）
  5. 注册中间件: CORS → AuthMiddleware → WorkspaceContextMiddleware → http_tracing_middleware
  6. 注册 15 个路由模块
```

### Step 1: 用户请求 → 意图分类 → 创建任务

```text
POST /api/v1/interact
  Body: { message: "帮我设计一个电商平台的技术方案，要求支持高并发..." }

  _classify_intent(req):
    IntentClassifier.classify(message)
      → 规则命中 GENERATION_PATTERNS → intent=complex_generation, confidence=0.85

  _route_sync: intent == COMPLEX_GENERATION → _create_generation_task:
    user_role = current_user.team_memberships[0].role.name
    task_id = await task_manager.create_task(prd_raw, prd_file_type, workspace_id,
                                             user_id, user_role, orchestrator)
  → 返回 InteractResponse{ intent:"complex_generation", message:"已创建生成任务: {task_id}",
                           task_id, session_id }
```

### Step 2: TaskManager.create_task

```text
create_task():
  1. task_id = uuid4(); thread_id = uuid4()（独立，用于 LangGraph checkpoint）
  2. task_record = {task_id, status:"running", progress:0.0, stage:"", interrupt_stage:"",
                    result:None, evaluation:None, error:None, created_at, updated_at,
                    thread_id, orchestrator}
  3. self._tasks[task_id] = task_record（asyncio.Lock 保护）
  4. TASKS_TOTAL.labels("created").inc()            # 指标埋点
  5. EventBus.publish("task:{task_id}", task.created)
  6. asyncio.create_task(_execute_task(...))        # 不阻塞 HTTP 响应
  7. return task_id
```

### Step 3: _execute_task

```text
_execute_task():
  1. initial_state = make_initial_state(task_id, prd_raw, prd_file_type, workspace_id,
                                        user_id, user_role, permissions)
  2. config = {"configurable": {"thread_id": thread_id}}
  3. async for step_state in orchestrator.astream(initial_state, config):
       # 每节点执行完 → LangGraph 自动写 checkpointer（PostgresSaver）
       # TaskManager 读 progress/stage → EventBus 推送 task.progress
  4. 结束后:
       final_state["status"] == "complete" → _update_result（写 result/evaluation，
           推送 task.progress(1.0) + task.status + done）
       final_state 仍 "running"（被 interrupt 暂停）→ 置 status="paused" +
           interrupt_stage，推送 task.review_required + task.status
   异常 → _mark_failed（TASKS_TOTAL("failed") + TASKS_DURATION，推送 error）
```

### Step 4: 主编排图逐节点执行

#### 节点 4.1: `classify` — 意图分类（幂等）

```text
IntentClassifyNode.run(state):
  state["intent"] 已存在 → 跳过（interact 预写）
  否则用 prd_raw 分类 → 写 intent / intent_confidence / intent_sub

route_by_intent(state) → "kg_retrieve" → 路由到 retrieve_memory
PostgresSaver: 写 checkpoint
```

#### 节点 4.2: `retrieve_memory` — 历史记忆检索

```text
RetrieveMemoryNode.run(state):
  从 _history_messages 取历史 → MemoryRetriever.retrieve(query=prd_raw[:500],
      messages, strategy="hybrid", top_k=10)
  → 写 retrieved_memories（新任务无历史 → 空列表）
  checkpoint
```

#### 节点 4.3: `knowledge_retrieval` — 知识库检索

```text
KnowledgeRetrievalNode.run(state):
  1. DecisionRecorder.start_trace(task_id)（Block F 行为回放）
  2. prd_raw 为空 → knowledge_context=None, progress=0.10，跳过
  3. RetrievalPipeline.retrieve(query=prd_raw[:500], mode="hybrid", top_k=10, workspace_id)
       内部: IntentRouter → QueryRewriter → QueryEnricher → 反思循环
             (LocalSearch 双路 + GlobalSearch + RRFFusion → ReflectionJudge → ReRanker → Compressor)
  4. 失败 → 降级 knowledge_context=None（不阻断）
  5. state["knowledge_context"] = ctx; progress = 0.10
  checkpoint
```

#### 节点 4.4: `analysis` — 需求分析（AnalysisAdapter）

```text
AnalysisAdapter.run(state):
  1. 提取输入: {prd_raw, knowledge_context, system_prompt(租户 PromptManager)}
  2. analysis_graph.ainvoke(input):
       parse → lang_detect → requirement → constraint → dependency → domain
       → quality → effort → stakeholder → clarity → assemble
  3. 写回: analysis_result / extracted_requirements / extracted_constraints
  4. progress = 0.25
  checkpoint
```

#### 节点 4.5: `analysis` 后条件路由（needs_review）

```text
needs_review(state):
  tenant_context.settings["auto_approve"]==True 或 user_role=="admin" → "skip_review"
  否则 → "review_needed" → analysis_human_review
```

#### 节点 4.6: `analysis_human_review` — 人工审核

```text
HumanReviewNode("analysis").run(state):
  review_context = {stage:"analysis", task_id, description:"分析结果审核",
                    data: {analysis_result, requirements_count, constraints_count}}
  feedback = interrupt(review_context)      # ⚠️ 图执行暂停，写 checkpoint

TaskManager 检测到 astream 结束且 status 仍 running:
  → 置 paused + interrupt_stage，推送 task.review_required + task.status(paused)
  ── 等待人工操作 ──
用户在前端审核通过:
  POST /api/v1/review/{task_id}/analysis 或
  POST /api/v1/tasks/{task_id}/stream-review（流式恢复）
  → task_manager.resolve_review(task_id, "analysis", decision, comment)
  → 置 status="resuming" → asyncio.create_task(_resume_task(...))

_resume_task:
  async for step_state in orchestrator.astream(
      Command(resume={"decision": "approved", "comment": "..."}), config):
    # LangGraph 从 checkpointer 加载 → interrupt() 返回 resume_value
    # decision != "needs_changes" → status="running" → 继续执行
  → 下一个节点: planning
```

#### 节点 4.7: `planning` — 架构规划（PlanningAdapter）

```text
PlanningAdapter.run(state):
  1. 输入: {analysis_result, knowledge_context, evaluation_feedback(迭代时)}
  2. planning_graph.ainvoke(input):
       knowledge_augment → pattern_recommend → pattern_confirm → tech_stack_select
       → component_decompose → cost_estimator → timeline_planner → skill_gap_analyzer
       → risk_quantifier → data_arch_design → api_planning → deployment_planning
       → self_check(→回退 pattern_recommend 或通过) → assemble
  3. 写回: planning_result / component_decomposition / tech_stack_choices
  4. progress = 0.50
  checkpoint
```

#### 节点 4.8: `planning_human_review` — 规划审核

```text
（与 analysis_human_review 相同流程）
  HumanReviewNode("planning") → interrupt() 暂停 → 人工审核 → Command(resume) 恢复
  → 继续到 generation
```

#### 节点 4.9: `generation` — 方案生成（GenerationAdapter）

```text
GenerationAdapter.run(state):
  1. 输入: {planning_result, analysis_result, section_contents(续写), export_formats,
            task_id(SSE), evaluation_feedback, system_prompt, claims_constraints}
  2. generation_graph.ainvoke(input):
       outline（选模板）→ [fan_out_sections → section_writer × n 并行（流式 + SSE）]
       → diagram → code_scaffold → consistency → revision → assemble → export
       SectionWriterNode 流式: async for token in llm.stream_complete(...):
           EventBus.publish("task:{task_id}", generation.section / generation.chunk)
  3. 写回: generation_result / section_contents / export_formats
  4. progress = 0.75
  checkpoint
```

#### 节点 4.10: `evaluation` — 质量评测（EvaluationAdapter）

```text
EvaluationAdapter.run(state):
  1. 输入: {analysis_result, planning_result, generation_result}
  2. evaluation_graph.ainvoke(input):
       fan_out_evaluators → [9 个评测节点 Send 并行] → scoring（LLM 补全 + 校准）
  3. 写回: evaluation_report; iteration_count += 1
  4. progress = 0.90
  checkpoint
```

#### 节点 4.11: `IterationDecider` — 迭代决策

```text
IterationDecider.run(state):
  根据 overall_score / dimension_scores / iteration_count / max_iterations:
    ≥85 或达 max_iterations → final_assembly
    ≥70 且 consistency<70 → generation（重生成）
    ≥70 且 feasibility<70 → planning（重规划）
    ≥70 其余 → final_assembly
    <70 且有 critical_issues → analysis_human_review（人工介入）
    <70 其余 → planning（重规划）
```

#### 节点 4.12: `final_assembly` — 最终组装

```text
FinalAssemblyNode.run(state):
  status="complete"; progress=1.0
  DecisionRecorder.end_trace(task_id)
  integration_hub.notify(event="task.completed", payload={task_id, workspace_id, status, progress},
                         sender=WebhookSender())   # 失败不阻断
  checkpoint
```

#### 节点 4.13: `compress_memory` — 记忆压缩

```text
CompressMemoryNode.run(state):
  _history_messages → ContextCompressor.compress(messages)（summarize→rolling→truncate）
  → 写 compressed_context（超限才压缩）
  checkpoint
```

#### 节点 4.14: `save_session` — 会话持久化

```text
SaveSessionNode.run(state):
  提取摘要: 优先 chat_response[:200]，否则 generation_result.summary
  提取分数: evaluation_report.overall_score
  副作用: 发布 task.saved 事件（task_id/status/score/summary）
  ⚠️ 注: 实际代码仅发 SSE 事件，未看到调用 session_service 持久化 DB（见 21）
  checkpoint
```

#### 节点 4.15: END — 流终止

```text
LangGraph 到达 END → astream 循环结束
TaskManager._update_result:
  status="complete"; progress=1.0; result=generation_result; evaluation=evaluation_report
  TASKS_TOTAL.labels("completed").inc() + TASKS_DURATION.observe(duration)
  推送: task.progress(1.0) + task.status(complete) + done(task_id, result_summary)
```

---

## 十、chat / knowledge_qa / clarification 路径全链路

### 10.1 chat 路径（同步）

```text
POST /api/v1/interact { message: "你好，你是谁？" }
  _classify_intent → IntentClassifier → chat, confidence=0.8
  _route_sync → intent != DOCUMENT_ANALYSIS / COMPLEX_GENERATION → _graph_sync:
    1. task_id = uuid4(); initial_state = make_initial_state(...)
    2. 预写 intent="chat"（图内 classify 幂等跳过）
    3. orchestrator.ainvoke(initial_state, config)
       → classify → route_by_intent("chat") → chat_node:
           ChatNode.run: gateway.stream_complete(prompt=prd_raw, task_type="chat",
               temperature=0.7, max_tokens=1024)
               SSE（经 _runtime.event_bus）: chat.status → 逐 token chat.chunk → chat.done
           → chat_response; status="complete"; progress=1.0
       → save_session → END
    4. 返回 InteractResponse{ intent:"chat", message: chat_response }
  图异常 → 降级 default_gateway.complete 直接回答（confidence=0.5）
```

### 10.2 knowledge_qa 路径（同步）

```text
POST /api/v1/interact { message: "这个项目中有哪些关于用户服务的架构设计？" }
  _classify_intent → knowledge_qa
  _graph_sync → classify → route_by_intent("knowledge_qa") → retrieve_node:
      KnowledgeQANode.run:
        阶段1 检索: pipeline.retrieve(query, workspace_id, top_k=5)
            拼 global_summary + results[:5].text
            SSE: qna.status(phase=retrieving → retrieved, sources=[{id,score}])
            检索失败降级直接回答
        阶段2 生成: 有 context → "根据以下知识库内容…" prompt
            gateway.stream_complete(task_type="knowledge_qa", temperature=0.5, max_tokens=2048)
            SSE: qna.chunk 逐 token
        → chat_response; status="complete"; progress=1.0
        SSE: qna.done(content_length + sources)
      → save_session → END
```

### 10.3 clarification 路径

```text
POST /api/v1/interact { message: "请补充需求细节" }（命中 CLARIFICATION）
  _graph_sync → classify → route_by_intent("clarification") → clarify_node:
      ClarifyNode.run: 不调 LLM
        SSE: chat.clarify(message + hint)
        status="clarification_needed"; progress=1.0; 固定提示文案
      → clarify_node → END（不经过 save_session）
```

---

## 十一、document_analysis / URL 文档路径全链路

### 11.1 doc_id 文档分析（同步）

```text
POST /api/v1/interact { message: "请分析这份文档", doc_id: "doc-001" }
  _classify_intent: 携带 doc_id → document_analysis（强信号 0.9）
  _route_sync → _document_analysis_sync:
    1. 非 generate、无 url → doc_id 分支
    2. _load_document_text:
         document_service.get_document_content(session, doc_id)  # 原始字节
         multi_format_loader.extract_text(raw, filename)          # 真实正文（非预览占位）
    3. _analyze_document(text, instruction, source_label):
         default_gateway.complete(prompt=_build_document_prompt(...),
             task_type="document_analysis", temperature=0.3, max_tokens=2048)
    4. 返回 InteractResponse{ intent:"document_analysis", message: 分析结果 }
```

### 11.2 URL 文档分析（SSRF 防护 + 入库）

```text
POST /api/v1/interact { message: "分析这个页面", url: "https://example.com/doc" }
  → document_analysis
  _document_analysis_sync → url 分支:
    1. _ingest_url_document:
         UrlDocumentService.fetch_content(url)（SSRF 校验 → WebLoader.fetch）
         UrlDocumentService.ingest(...)（入库 uploaded_documents, file_type="url", source_url）
    2. _analyze_document(text, ...) → 摘要
    3. 返回分析结果
```

### 11.3 URL 一键生成 TSD

```text
POST /api/v1/interact { message: "", url: "https://example.com/prd", generate: true }
  → document_analysis
  _document_analysis_sync → generate 分支:
    _create_generation_task_from_url:
      抓取 → 文本作为 prd_raw → task_manager.create_task（complex_generation 异步任务）
    → 返回 InteractResponse{ intent:"complex_generation", task_id }
```

### 11.4 流式文档分析（stream=true）

```text
POST /api/v1/interact { ..., stream: true }
  → _route_stream（StreamingResponse）
  document_analysis 流式: 抓取/读文档 → LLM 流式生成 → SSE 推送 chat.chunk / qna.chunk 等
  complex_generation 流式: 复用 /tasks/{task_id}/events 订阅
```

---

## 十二、断点恢复与 Human-in-the-Loop 全链路

### 12.1 完整时序图

```text
用户          FastAPI          TaskManager          LangGraph          PostgresSaver
 │  POST /interact │                  │                    │                   │
 │──────────────→│ create_task()     │                    │                   │
 │               │─────────────────→│ _execute_task()    │                   │
 │               │                  │ astream(init)      │                   │
 │               │                  │───────────────────→│                   │
 │               │                  │                    │ classify...        │
 │               │                  │ progress:0.25      │ analysis           │
 │               │                  │←───────────────────│                   │
 │               │                  │                    │ needs_review       │
 │               │                  │                    │ → review_needed    │
 │               │                  │                    │ analysis_human     │
 │               │                  │                    │ _review interrupt()│
 │               │                  │                    │──────────────────→│ save checkpoint
 │               │                  │ status:paused      │←──────────────────│
 │               │                  │←───────────────────│                   │
 │               │  SSE: review_required + status        │                   │
 │               │←─────────────────│                    │                   │
 │  [用户审核通过]                    │                    │                   │
 │ POST /review  │                  │                    │                   │
 │──────────────→│ resolve_review() │                    │                   │
 │               │─────────────────→│ _resume_task()     │                   │
 │               │                  │ astream(Command(   │                   │
 │               │                  │  resume=feedback)) │                   │
 │               │                  │───────────────────→│                   │
 │               │                  │                    │ load checkpoint   │
 │               │                  │                    │ interrupt() 返回  │
 │               │                  │                    │ → 继续 planning... │
 │               │                  │ progress:0.50      │                   │
 │               │                  │←───────────────────│                   │
 │               │                  │ ... 继续 ...       │                   │
 │               │                  │ done               │ save_session      │
 │               │  SSE: done       │←───────────────────│                   │
 │               │←─────────────────│                    │                   │
```

### 12.2 崩溃恢复场景

```text
场景: 服务在 generation 节点执行中崩溃

崩溃前: PostgresSaver 已存 checkpoint_0..checkpoint_n（每节点执行后）
       sessions 表: thread_id / status="running"（若已创建会话）

重启后恢复:
  1. lifespan → 重建 PostgresSaver + 重编译主编排图
  2. 找到 status="running" 的会话 → thread_id
  3. POST /api/v1/tasks/{task_id}/resume  → TaskManager
       orchestrator.astream(None, {"configurable":{"thread_id"}})
       # 传入 None（非 Command(resume)）→ LangGraph 从最近 checkpoint 恢复，
       # 重放已完成的节点（自动跳过），继续未完成的
```

### 12.3 审核 API

```text
GET  /api/v1/review/pending                 → 列出所有 paused 任务
POST /api/v1/review/{task_id}/{stage}       → 提交审核（stage: analysis/planning;
                                                decision: approved/needs_changes）
POST /api/v1/tasks/{task_id}/stream-review  → 审核 + 流式恢复（SSE，须 paused 状态）
```

---

## 十三、历史消息处理全链路

### 13.1 会话生命周期

```text
1. 创建会话:  POST /api/v1/sessions
   → SessionRepository.create_session()（自动生成 thread_id=uuid4()）→ 写 sessions 表

2. 发送消息（绑定会话）:
   POST /api/v1/interact { message, session_id }
   → 取 session.thread_id → config={"configurable":{"thread_id"}}
   → orchestrator.ainvoke/astream
       ├─ retrieve_memory 节点: 加载 sessions/session_messages 历史 → MemoryRetriever
       ├─ ... 中间节点 ...
       └─ save_session 节点: （SSE task.saved；DB 写入见 21 已知问题）

3. 查询历史:
   GET /api/v1/sessions?page=&status=       → 分页列表（last_message_at DESC）
   GET /api/v1/sessions/{id}/messages       → 消息列表（created_at ASC, 分页）

4. 搜索:  GET /api/v1/sessions/search/messages?q=
   → PostgreSQL FTS: to_tsvector('simple', content) @@ plainto_tsquery('simple', q) + ts_rank

5. 导出:  GET /api/v1/sessions/{id}/export?format=markdown|json

6. 老化清理: POST /api/v1/sessions/cleanup?plan= 或 Celery cleanup_expired_sessions
   → SessionCleanupPolicy: free 30天 / pro 180天 / enterprise 不限（软删）

7. 续接会话:
   POST /api/v1/interact { message: "继续上次讨论...", session_id }
   → 相同 thread_id → LangGraph 自动加载历史 checkpoint + retrieve_memory 获取记忆
```

### 13.2 MemoryRetriever 四种策略对比

```text
场景: 用户在 50 轮对话后问 "之前讨论的那个数据库方案是什么？"

策略 1: recency（最近优先）: exp(-hours_ago/24)，24h 半衰期
策略 2: relevance（语义相关）: 关键词重叠率（实际为纯词重叠，向量未用）
策略 3: importance（重要优先）: LLM 打分（0-1，无 gateway 默认 0.5）
策略 4: hybrid（融合）: 0.3*recency + 0.4*relevance + 0.3*importance（默认）
```

---

## 十四、SSE 流式推送全链路

### 14.1 订阅与推送

```text
GET /api/v1/tasks/{task_id}/events:
  1. 校验任务存在（不存在 → 单条 error SSE）
  2. 构造初始快照 task.snapshot（task_id/status/progress/stage）
  3. sse_response(subscribe_task_events(channel, snapshot)):
       - 订阅 event_bus.subscribe("task:{task_id}")
       - 循环 asyncio.wait_for(queue.get(), 30s)：
            收到事件 → yield event.to_sse_line()；done/error 则 break
            超时 → yield keepalive
       - CancelledError/finally → unsubscribe（清理资源）

POST /api/v1/tasks/{task_id}/stream-review:
  校验 decision ∈ {approved, needs_changes}、任务 paused
  → task_manager.resolve_review → 返回 sse_response(subscribe_task_events(channel, review_event))
```

### 14.2 事件完整时间线（一次 complex_generation 任务）

```text
时间   事件类型               Payload
────   ──────────────────     ──────────────────────────────────
0s     task.created           {task_id, status:"running", workspace_id}
0s     task.snapshot          {task_id, status, progress, stage}（订阅时）
       task.progress          {task_id, progress, stage}（每节点执行后）
       task.status            {status}
       task.log               {level, message}
15s    task.review_required   {task_id, stage:"analysis"}
15s    task.status            {status:"paused"}
────   等待人工审核 ────
       task.review_resolved   {task_id, stage, decision}
       task.status            {status:"resuming"}
       task.progress          {progress, stage:"planning"}
       task.review_required   {stage:"planning"}
────   等待人工审核 ────
       task.review_resolved   {decision}
45s    task.progress          {progress:0.75, stage:"generation"}
       generation.section     {section, status:"generating"}
       generation.chunk       {content, section}（流式）
       generation.section     {section, status:"done"}
       ... （14 个章节逐节推送）
60s    task.progress          {progress:0.90, stage:"evaluation"}
       task.progress          {progress:1.0, stage:"complete"}
       task.status            {status:"complete"}
       task.saved             {task_id, status, score, summary}
66s    done                   {task_id, result_summary}
```

### 14.3 流式生成集成（SectionWriterNode）

```text
SectionWriterNode 流式生成:
  ├─ llm.astream(prompt)（GatewayChatModel 流式 → gateway.stream_complete）
  ├─ 每 200 字符: EventBus.publish("task:{task_id}", generation.chunk {content, section})
  ├─ 章节完成:    EventBus.publish(generation.section {section, status:"done", content_length})
  └─ 所有章节:    经 reducer merge_contents 合并进 section_contents
```

---

## 十五、LLM 调用全链路（Gateway + LangChain 适配器）

### 15.1 两种调用方式对比

```text
方式 1: 直接 Gateway 调用
  使用场景: TaskManager / ChatNode / KnowledgeQANode / document_analysis / 评测 judge
  代码:  response = await gateway.complete(prompt=..., task_type="chat",
                                          workspace_id=..., layer=..., node=...)

方式 2: LangChain 适配器调用
  使用场景: Analysis / Planning / Generation / Evaluation 层节点内部
  代码:  llm = GatewayChatModel(task_type="analysis", layer="analysis", node="...")
         chain = ChatPromptTemplate.from_messages([...]) | llm | PydanticOutputParser(...)
         result = await chain.ainvoke({"input": "..."})
  优势:  节点内部可用 LangChain 生态（PromptTemplate / OutputParser / bind_tools）
         同时保留 Gateway 全部生产级能力（限流/缓存/熔断/护栏/成本追踪）
```

### 15.2 Gateway.complete() 完整链路

```python
async def complete(self, prompt, task_type="default", workspace_id="",
                   layer="", node="", **kwargs) -> LLMResponse:
    with tracer.start_as_current_span(f"gateway.complete.{task_type}", kind=SpanKind.CLIENT):
        # 0. 前置护栏
        input_results = await self.guardrails.check_input(prompt, guard_context)
        for r in input_results:
            if r.blocked:  LLM_CALL_TOTAL.inc(); return blocked_response

        # 1. 速率限制
        rate_result = await self.rate_limiter.check(workspace_id)
        if not rate_result["allowed"]:  LLM_CALL_TOTAL.inc(); return rate_limited_response

        # 2. 模型路由
        model_config, model_name = self.config_manager.resolve_model(task_type)

        # 3. 预算检查（自动降级）
        if await self.budget_controller.check_and_record(workspace_id, 0, model_name) \
                .get("should_downgrade"):
            model_name = self._get_low_cost_model(model_name)   # → gpt-4o-mini/deepseek-chat

        # 指标追踪（含缓存命中/失败路径）
        with track_llm_call(model_name, layer, node) as token_info:
            # 4. 语义缓存
            cache_key = self.cache.make_key(prompt, task_type)
            if (cached := self.cache.get(cache_key)) is not None:
                return LLMResponse(cached=True, cost=0, ...)

            # 5. Circuit Breaker + Failover 链
            if cb and not cb.is_available:  # 当前 Provider 已熔断 → 走 Failover
                span.set_attribute("circuit_broken", True)
            response, model_name = await self._failover_call(prompt, kwargs)
            if response is None:  LLM_CALL_TOTAL.inc(); return all_failed_response

            # 7. 后置护栏
            output_results = await self.guardrails.check_output(response.content, ...)
            #  blocked + masked_text → 替换；否则标记 [输出被护栏拦截]

            # 8. 缓存 / 成本 / 预算 / 速率
            self.cache.set(cache_key, response.content)
            self.cost_tracker.record(model=model_name, input_tokens=..., output_tokens=...)
            LLM_COST_TOTAL.labels(model_name).inc(response.cost)
            await self.budget_controller.check_and_record(ws, response.cost, model_name)
            await self.rate_limiter.record(ws, tokens)
            token_info["input_tokens"] = ...; token_info["output_tokens"] = ...
            return response
```

### 15.3 GatewayChatModel 适配器（app/llm_gateway/langchain_adapter.py）

```python
class GatewayChatModel(BaseChatModel):
    gateway: Any = None          # 未提供时自动从 app.llm_gateway import gateway
    default_model: str = "deepseek-chat"
    task_type: str = "default"
    layer: str = ""
    node: str = ""

    def _generate(messages, stop, run_manager, **kwargs) -> ChatResult:
        # 同步路径: 有事件循环 → ThreadPoolExecutor 里 asyncio.run(_agenerate)
        #           无事件循环 → asyncio.run(_agenerate)

    async def _agenerate(messages, stop, run_manager, **kwargs) -> ChatResult:
        # LangChain messages → prompt（_messages_to_prompt）
        # gateway.complete(prompt, task_type, layer, node, **kwargs)
        # → ChatResult(generations=[ChatGeneration(AIMessage(content))])

    def _astream(...) -> Iterator[ChatGenerationChunk]:
        # gateway.stream_complete 逐 token → AIMessageChunk

    def bind_tools(tools):
        # Function Calling 支持（tool 生态当前未启用）
```

### 15.4 LLM 调用的完整护栏 + 降级链路

```text
用户 Prompt
    │
    ▼
pre_llm 护栏: PromptInjectionGuardrail → PIIDetectorGuardrail → TimeoutGuardrail(CircuitBreaker)
    │  blocked → 返回拦截响应（并计数）
    ▼
速率限制 → 模型路由 → 预算降级 → 语义缓存
    ▼
Circuit Breaker + Failover 链（deepseek-chat → gpt-4o-mini）
    │  熔断的 Provider 自动跳过；全部不可用 → AllProvidersUnavailableError → 降级响应
    ▼
LLM 调用（OpenAI SDK 兼容 Provider）+ OTel Span + track_llm_call 指标
    ▼
post_llm 护栏: ContentSafetyGuardrail → OutputValidatorGuardrail → EmptyResponseGuardrail
    │  → RetryDecisionGuardrail（决定 retry/fallback/continue）
    ▼
设置缓存 / 成本追踪（CostTracker + llm_call_logs）/ 预算 / 速率记录
    ▼
返回 LLMResponse{content, model, cached, cost, input_tokens, output_tokens, metadata}
```

---

## 十六、LangGraph 与 LangChain 的分工设计

### 16.1 明确边界

```text
LangGraph 的职责:
  1. 图结构定义（StateGraph + add_node + add_edge）
  2. 条件路由（add_conditional_edges + route 函数 / Command 路由）
  3. 人工中断恢复（interrupt() + Command(resume=...))
  4. 状态持久化（PostgresSaver checkpoint）
  5. 并行扇出（Send() API: Evaluation 9 节点 + Generation section_writer）

LangGraph 不负责: LLM 调用本身 / Prompt 构建 / 输出解析 / Tool Calling

LangChain 的职责:
  1. Prompt 模板（ChatPromptTemplate / MessagesPlaceholder）
  2. 结构化输出（PydanticOutputParser / with_structured_output）
  3. Tool Calling（bind_tools + ToolMessage，当前工具生态已废弃未用）
  4. LLM 调用适配（GatewayChatModel extends BaseChatModel）
  5. LCEL 链式组合（prompt | llm | parser）

LangChain 不负责: Agent 编排（这是 LangGraph 的职责）
```

### 16.2 每一层使用什么

| 层级 | LangGraph | LangChain |
|------|-----------|-----------|
| 主编排图 | ✅ StateGraph / 条件路由 / interrupt/resume / PostgresSaver / Send | ❌ |
| 4 个 Agent Layer | ✅ 各自 StateGraph（含节点链 + 条件边 + Send 扇出） | ✅ ChatPromptTemplate + GatewayChatModel + PydanticOutputParser |
| Adapter 层 | ❌ 纯 Python 状态映射 | ❌ |
| TaskManager | ✅ astream / Command(resume) | ❌ |
| ChatNode / KnowledgeQANode | ✅ 图内节点 | ✅ GatewayChatModel.stream_complete |
| GatewayChatModel | ❌ | ✅ BaseChatModel 实现 |
| LLM Gateway | ❌ | ✅ GatewayChatModel 内部委托 |

### 16.3 为什么不用 LangChain AgentExecutor

```text
tech-stack.yml 黑名单: langchain / langchain-community / langchain-openai / langchain-anthropic ...
原因:
  1. AgentExecutor 是黑盒 ReAct 循环，难以精确控制
  2. 使用 LangGraph StateGraph 显式定义每个步骤，完全可控
  3. 使用 GatewayChatModel 替代 langchain-openai 的 ChatOpenAI（保留成本/限流/缓存/护栏）
  4. langchain-core 被使用（ChatPromptTemplate / PydanticOutputParser），与 tech-stack 声明存在偏差（见 21）
```

---

## 十七、关键技术决策与架构原则

### 17.1 架构原则

```text
原则 1: 组件逻辑不变，仅解决接线问题
  LLM Gateway / Guardrails / ContextCompressor / MemoryRetriever / SessionHistoryService
  / EventBus 的现有实现逻辑保持不变，仅接入 LangGraph 图中作为节点调用。

原则 2: 错误处理进入护栏体系
  错误处理是护栏系统的一个维度（TimeoutGuardrail / EmptyResponseGuardrail / RetryDecisionGuardrail）。

原则 3: Config / State / Runtime 三层分离
  - Config: 启动时加载只读（max_iterations=3）
  - State:  LangGraph checkpoint 自动持久化
  - Runtime: 每次请求注入，不参与序列化（⚠️ 当前 RuntimeInjector 未接线，见 21）

原则 4: 4 层 Agent 100% 通过 contracts 解耦
  层与层之间不直接 import，通过 Adapter 做状态映射；每层可独立编译、独立测试。

原则 5: 禁止在 Layer Node 内部直接引用 OrchestratorState
  破坏 Layer 独立性，使 Layer 单元测试失效。

原则 6: 统一交互入口（Block E B1）
  /chat、/generate、/qna/stream 等端点全部收敛到 /api/v1/interact，意图判定唯一来源，
  图内 classify 节点幂等跳过双实现。

原则 7: 未兑现的复杂逻辑及时简化/删除（R5 豁免场景）
  社区检测（Leiden）、CLIP 多模态、协作文档、CSV 双通路、搜索引擎回退均已删除，
  避免"半实现"伪能力。Global Search 保留轻量宏观总结。
```

### 17.2 关键数据流决策

```text
决策 1: session.thread_id = LangGraph checkpoint thread_id
  好处: 会话历史与 LangGraph 状态持久化完全绑定，续接时自动恢复
  代价: sessions 表增加 thread_id 字段（迁移 d4e5f6g7h8i9）

决策 2: PostgresSaver 替代 MemorySaver（失败降级 MemorySaver）
  好处: 崩溃恢复 / 多线程安全 / Time-Travel 调试
  代价: 每次 checkpoint 一次 PG 写入（LangGraph 已优化为批量）

决策 3: astream 替代 ainvoke 做 TaskManager 执行
  好处: 实时进度推送、节点级可观测性
  代价: TaskManager 复杂度增加

决策 4: Command(resume=value) 替代直接传参做 resume
  好处: 正确处理 checkpoint 回放，不丢失中间状态
  代价: interrupt() 时需正确构造 resume_value

决策 5: GatewayChatModel 替代 langchain-openai 的 ChatOpenAI
  好处: 保留成本追踪/限流/缓存/熔断/护栏全部能力
  代价: 需维护适配器代码

决策 6: Evaluation 用 Send() 并行扇出（Block G 已实现）
  9 个评测节点并行 → 总耗时 = max(单节点) 而非 sum
```

### 17.3 性能优化策略

```text
1. 语义缓存:  相同 prompt+task_type 命中缓存，跳过 LLM 调用（TTL 1h）
2. 预算控制:  月预算超 90% → 自动降级到低成本模型
3. Session 老化清理: free 30天 / pro 180天
4. ContextCompressor: token 超限自动压缩（summarize→rolling→truncate）
5. Failover 链: 主 Provider 不可用自动切换，恢复自动切回
6. Circuit Breaker: 连续失败熔断，超时半开试探
7. Send() 并行扇出: Evaluation 9 节点 + Generation section_writer 并行
8. 知识层: 语义缓存 + 反思纠偏 + 压缩器控制 token 预算
```

---

## 十八、API 端点完整清单

> 全部端点统一前缀 `/api/v1`。**`/interact` 是统一交互入口**。

### 18.1 认证（app/api/routes/auth.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/auth/register` | 注册（自动建 org + 个人 workspace + admin 角色 + TeamMember），返回双 token |
| POST | `/auth/login` | 登录，返回双 token（携带 org_id/ws_id/permissions） |
| POST | `/auth/refresh` | refresh_token 换新 access_token |
| POST | `/auth/logout` | 登出 |
| GET | `/auth/me` | 当前用户信息 |

### 18.2 工作空间（workspace.py / workspace_members.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/workspaces` | 创建工作空间（自动赋 admin 角色） |
| GET | `/workspaces` | 列出当前用户 workspace（排除 is_archived） |
| GET | `/workspaces/{workspace_id}` | 详情 |
| PUT | `/workspaces/{workspace_id}` | 更新 name/slug/is_archived |
| DELETE | `/workspaces/{workspace_id}` | 归档（软删） |
| POST | `/workspaces/{ws}/members` | 添加成员 |
| DELETE | `/workspaces/{ws}/members/{member_user_id}` | 移除成员 |

### 18.3 模型配置（model_config.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/model-config` | 查所有模型配置（API Key 掩码）+ routing_rules |
| PUT | `/model-config` | 动态更新模型配置（立即生效） |
| PUT | `/model-config/routing` | 更新路由规则 |
| DELETE | `/model-config/runtime` | 重置运行时配置回环境变量 |

### 18.4 知识库（knowledge.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/knowledge/build` | 上传 .md 构建知识图谱 |
| POST | `/knowledge/build-from-path` | 从服务器路径构建图谱 |
| POST | `/knowledge/search` | 检索（mode: local/global/hybrid, top_k） |

### 18.5 任务（generate.py / stream_generate.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/tasks/{task_id}` | 任务状态查询（旧 /generate 端点已删，complex_generation 走 /interact） |
| GET | `/tasks/{task_id}/events` | SSE 事件流订阅（task.snapshot 初始） |
| POST | `/tasks/{task_id}/stream-review` | 审核 + 流式恢复（SSE） |

### 18.6 审核（review.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/review/pending` | 列出待审核任务（paused） |
| POST | `/review/{task_id}/{stage}` | 提交审核（stage: analysis/planning；decision: approved/needs_changes） |

### 18.7 评测（evaluate.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/evaluate` | 评测生成结果（调 evaluation_graph，返回 evaluation_report + dimension_scores） |

### 18.8 会话（sessions.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/sessions` | 创建会话 |
| GET | `/sessions` | 列表（分页 + 筛选 + q 搜索） |
| GET | `/sessions/{session_id}` | 详情 |
| PUT | `/sessions/{session_id}` | 更新 |
| DELETE | `/sessions/{session_id}` | 软删除 |
| POST | `/sessions/{session_id}/messages` | 添加消息 |
| GET | `/sessions/{session_id}/messages` | 消息列表 |
| GET | `/sessions/search/messages` | 全文搜索消息（FTS） |
| GET | `/sessions/{session_id}/export` | 导出（fmt: markdown/json） |
| POST | `/sessions/cleanup` | 老化清理（plan: free/pro/enterprise） |

### 18.9 文档管理（documents.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/documents/upload` | 上传文档（SHA-256 去重，返回 deduplicated；自动触发入图） |
| GET | `/documents` | 列表/搜索（q 走全文搜索） |
| GET | `/documents/stats` | 文档统计 |
| GET | `/documents/{document_id}` | 详情 |
| DELETE | `/documents/{document_id}` | 删除（软删 + MinIO 删） |
| GET | `/documents/{document_id}/preview` | 预览 |
| POST | `/documents/{document_id}/reindex` | 重索引 |

### 18.10 Web 索引（web_indexing.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/web-indexing/fetch` | 抓取单 URL（默认 index_to_kg=True 增量写图谱） |
| POST | `/web-indexing/crawl` | 同域递归爬取 |
| POST | `/web-indexing/sync` | 定时同步（ETag/Last-Modified 变更检测，force 可强制） |

### 18.11 集成（integrations.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/integrations/webhooks` | 注册 Webhook |
| DELETE | `/integrations/webhooks` | 注销 Webhook（event 查询参数） |
| POST | `/integrations/webhooks/test` | 测试连通性 |
| GET | `/integrations/webhooks` | 列出 Webhook |

### 18.12 批量（batch.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/batch/reindex` | 批量重索引 |
| POST | `/batch/regenerate` | 批量重新生成 |
| GET | `/batch/tasks/{task_id}` | 批量任务状态 |
| GET | `/batch/tasks` | 批量任务列表 |
| POST | `/batch/scheduler/trigger/{task_name}` | 立即触发定时任务 |

### 18.13 统一交互入口（interact.py）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/interact` | 意图分流：chat/knowledge_qa/clarification→主编排图；complex_generation→异步任务；document_analysis(url/doc_id)→文档分析；stream=true→SSE |

### 18.14 系统（main.py 顶层）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查（connections + gateway + model_config） |
| GET | `/api/v1/metrics` | Prometheus 指标（include_in_schema=False） |
| GET | `/` | 应用基本信息 |

---

## 十九、数据模型与数据库

### 19.1 SQLAlchemy ORM 模型（app/models/，10 张表）

| 模型 | 表 | 关键字段 |
|------|-----|---------|
| `User` | `users` | id, email(unique), display_name, hashed_password, auth_provider(默认jwt), auth_id, status, preferences(JSON)；uq_user_auth(auth_provider,auth_id)；关系 team_memberships |
| `Organization` | `organizations` | id, name, slug(unique), plan(默认free), settings(JSON)；关系 workspaces/roles |
| `Workspace` | `workspaces` | id, organization_id(FK), name, slug, knowledge_scope(默认workspace), is_archived；uq_org_workspace_slug |
| `Role` | `roles` | id, organization_id(FK,可空), name, is_system, permissions(JSON) |
| `TeamMember` | `team_members` | id, workspace_id(FK), user_id(FK), role_id(FK)；uq_workspace_user |
| `LLMCallLog` | `llm_call_logs` | id, task_id, workspace_id(FK), model, layer, node, input_tokens, output_tokens, cost(Numeric 10,6), latency_ms, cached, created_at |
| `BudgetConfig` | `budget_configs` | id, workspace_id(FK,unique), monthly_budget_usd, alert_threshold(默认0.90), auto_downgrade(默认True) |
| `Session` | `sessions` | id, workspace_id(FK), user_id(FK), title, session_type, status, source_prd_id, source_task_id, summary, message_count, token_count, cost_usd, rating, tags(JSON), last_message_at, deleted_at, **thread_id / checkpoint_ts / current_node / interrupt_stage（LangGraph 断点）**；uq_workspace_session |
| `SessionMessage` | `session_messages` | id, session_id(FK,CASCADE), user_id(FK), role, content, content_type, attachments(JSON), metadata(JSON), parent_message_id, **turn_index**, token_count, cost_usd, latency_ms, model_used, rating, created_at；uq_session_turn(session_id,turn_index) |
| `UploadedDocument` | `uploaded_documents` | 见 6.2（含 processing_status/file_hash/source_url 等） |

**base.py**：`Base(DeclarativeBase)`；`UUIDMixin.id`（String(36) 主键，uuid4）；`TimestampMixin`（created_at/updated_at）。

### 19.2 Alembic 迁移历史

| Revision | 文件名 | 内容 |
|----------|--------|------|
| `938e6d4dcfd6` | init_all_tables.py | 创建 10 张表 + 索引（sessions 5、messages 2、documents 6） |
| `a1b2c3d4e5f6` | add_block_e_tables.py | 类型修复：sessions.tags / uploaded_documents.tags ARRAY(String)→JSONB |
| `d4e5f6g7h8i9` | add_session_langgraph_fields.py | sessions 加 4 列：thread_id(索引)/checkpoint_ts/current_node/interrupt_stage |

### 19.3 Contracts 数据模型（contracts/）

**基础 @dataclass**：`ScoredDoc, RetrievalContext, Requirement, Constraint, AnalysisResult, TechChoice, Component, PlanningResult, GenerationResult, EvaluationReport`。

**Pydantic 增强模型**：

```text
RequirementDetail{id, type(functional/non_functional), category, priority(P0-P3),
                  description, actor, acceptance_criteria[], source_section}
ConstraintDetail{type(technical/performance/time/budget/compliance/team), description,
                 severity(must/should/could), source_section}
DocumentSection{title, level, content, subsections[]}（递归）
DependencyGraph{nodes[], edges[](from,to,relation)}
AnalysisResultDetail{project_name, summary, domain_tags[], requirements[], constraints[],
                     dependency_graph, confidence, stakeholders[](dict), clarity_issues[]}
PatternEval{pattern_name, match_score, strengths[], weaknesses[], complexity}
TechChoiceDetail{dimension, recommendation, reason, alternatives[], risks[]}
ComponentDetail{name, type(service/module/library), responsibility, key_functions[], dependencies[]}
PlanningResultDetail{architecture_pattern, tech_stack[], components[], component_diagram,
                     metadata(node_outputs)}
SectionOutline{section_id, title, level, description, estimated_tokens}
GenerationResultDetail{content, sections{}, mermaid_diagrams{}}
EvaluationReportDetail{overall_score, dimension_scores{}, conclusion(通过/预警通过/不通过),
                       p0_coverage, critical_issues[], recommendations[]}
```

**models.py（Block F 统一模型）**：`ModelType/ProviderType, ModelConfig, RoutingRule, TaskStatus/TaskType/Task, StructuredOutputConfig, TenantPrompt, PromptVersion, ABTestConfig, DecisionRecord, TraceTree, MemoryItem`。

---

## 二十、Docker 拓扑与配置

### 20.1 Docker Compose（10 个服务 + 4 卷 + 1 网络）

```yaml
services:
  postgres:       postgres:15         → 5432    用户 postgres/postgres，库 prd2tsd
  redis:          redis:7             → 6379
  minio:          minio/minio:latest  → 9000/9001(console)  root minioadmin/minioadmin
  neo4j:          neo4j:5             → 7700(7474)/7701(7687)  auth neo4j/neo4jpassword
  jaeger:         jaegertracing/all-in-one:latest → 16686(UI)/4317(OTLP gRPC)/4318(OTLP HTTP)
  prometheus:     prom/prometheus:latest → 9090    挂载 ./prometheus.yml
  grafana:        grafana/grafana:latest → 3000    挂载 ./storage/grafana/provisioning + dashboards
  api:            Dockerfile          → 8000    env 注入 DB/Redis/MinIO/Neo4j/OTEL
  celery-worker:  Dockerfile          → -       celery -A app.batch.tasks worker --concurrency=4
  celery-beat:    Dockerfile          → -       celery -A app.batch.scheduler beat
volumes:  pgdata
```

> **注意**：compose 中 postgres 为 15（tech-stack.yml 声明 16）；neo4j 映射到非标准端口 7700/7701（config.py `NEO4J_URI=bolt://localhost:7701`）。

### 20.2 依赖清单（requirements.txt / pyproject.toml）

| 类别 | 依赖 |
|------|------|
| AI Agent | langgraph>=1.2.0, langgraph-checkpoint-postgres>=2.0, langchain-core>=0.3.0 |
| Web | fastapi>=0.110, uvicorn[standard], python-multipart, jinja2>=3.1 |
| ORM/DB | sqlalchemy>=2.0, asyncpg, alembic, pgvector>=0.3.0 |
| Auth | python-jose[cryptography], passlib[bcrypt], bcrypt>=4.0 |
| LLM | openai>=1.0 |
| 评测 | **ragas==0.4.3（唯一精确锁版）** |
| 基础设施 | redis[hiredis]>=5.0, minio>=7.0, neo4j>=5.0 |
| 知识层 | sentence-transformers>=3.0, torch>=2.0, transformers>=4.40.0, cohere>=5.0 |
| 观测 | opentelemetry-api/sdk/exporter-otlp-proto-grpc>=1.20.0, prometheus-client>=0.19.0 |
| 任务队列 | celery>=5.3.0 |
| 文档导出 | markdown>=3.5, weasyprint>=60.0, fpdf2>=2.7, python-docx>=1.1, pypdf>=4.0 |
| 测试 | pytest>=8.0, pytest-asyncio, pytest-cov, ruff, mypy, aiosqlite |

### 20.3 工具链配置（pyproject.toml）

```text
[tool.ruff]  target py312, line-length 120；lint select=E,F,I,N,W,UP,B,C4,SIM；ignore=ANN,ARG,B008,B017,E402
[tool.mypy]  strict=true, ignore_missing_imports, warn_unused_ignores, disallow_untyped_defs
[tool.pytest] testpaths=tests, asyncio_mode=auto, python_files=test_*.py
```

---

## 二十一、已知问题与风险

> 基于 2026-08-13 代码审查的**实测**问题（区别于设计文档的理想描述）。

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | **RuntimeInjector 未接线**：`_runtime` 从未注入主编排图 | `chat_node`/`retrieve_node`/`clarify_node` 的 SSE 副作用（chat.chunk/qna.chunk 等）在图中实际不生效（event_bus=None）；`OrchestratorRuntime` 设计未落地 | 在 build_and_compile 前调用 RuntimeInjector.inject，或在节点内改为显式依赖注入 |
| 2 | **SaveSessionNode 语义偏差**：注释声称写 PG，实际仅发 `task.saved` SSE 事件 | 会话消息/摘要未真正持久化到 sessions/session_messages | 补上 session_service 持久化调用（此前修复移除了 `_runtime` 依赖，但未接回 session_service） |
| 3 | **IterationDecider 阈值硬编码**：85/70 未读 `OrchestratorConfig.evaluation_pass_threshold/replan_threshold` | 配置项失效 | 改为从 config 读取 |
| 4 | **EVENT_TYPES 不全**：`chat.status/chat.chunk/chat.done/chat.clarify/task.saved` 未登记 | SSE 文档/校验不一致 | 补全 EVENT_TYPES |
| 5 | **WebIndexer 悬空引用**：`batch/tasks.py` 的 `sync_web_resources` 导入不存在的 `WebIndexer` 类 | Celery 环境该任务必然 ImportError → retry | 实现 WebIndexer 或改为 WebSyncScheduler |
| 6 | **agents/tools/ ToolRegistry 已废弃但文件保留** | 代码库存在无调用死代码 | 彻底清理或迁移到 LangChain ToolNode |
| 7 | **ScoringNode 无显式加权公式**；`completeness` 维度无子节点 | 评分权重不可调，completeness 全靠 LLM 补 | 按需实现显式加权 |
| 8 | **ScoreCalibrator 仅实现历史比对**（平行评测为占位）；history 不持久化 | 校准能力打折 | 补平行评测/持久化 |
| 9 | **BuildStats 缺 `claims` 字段**（pipeline 传了但模型没有） | 访问 stats.claims 会失败 | 补字段 |
| 10 | **MemoryRetriever recency 用 now 计算 timestamp**；relevance 向量未用 | recency 实际全近 1.0，四策略退化 | 修复时间戳来源 |
| 11 | **ImplementabilityEvalNode 读不存在的 `node_outputs`**（不在 EvaluationState） | 实际走默认值分支 | 定义字段或注入 planning node_outputs |
| 12 | **tech-stack.yml 过时/矛盾**：celery/redis 同时在 forbidden 与 allowed；禁 langchain-core 但实际使用；声明 PG16 实为 15 | 合规测试与实现矛盾 | 更新 tech-stack.yml 为真实状态 |
| 13 | **search_claims / semantic_similarity_threshold / hybrid_top_k 定义未接线** | 死配置 | 清理或接线 |
| 14 | **决策回放记录粒度有限**：仅 start_trace/end_trace，中间节点未 record_decision | TraceTree 只有首尾 | 在各节点补 record_decision |
| 15 | **模型配置与认证模型重复定义**（auth/models.py 与 api/schemas/response.py 的 TokenResponse） | 维护成本 | 合并 |
| 16 | **迁移与 ORM 不一致**：roles.organization_id NOT NULL vs ORM nullable；team_members joined_at vs TimestampMixin.created_at | autogenerate 漂移风险 | 对齐 |
| 17 | **BatchTaskService 内存存储**（重启丢失） | 批量任务状态不持久 | 迁 PostgreSQL |
| 18 | **评测报告依赖有效 LLM API key**（DeepSeek/OpenAI 401 时无法真实评测） | 评测闭环需配置密钥 | 配置有效 key 后执行 |

---

## 二十二、术语表与关键数字速查

### 22.1 术语表

| 术语 | 英文 | 含义 |
|------|------|------|
| 主编排图 | Orchestrator Graph | LangGraph StateGraph，串联 4 个 Agent Layer 的主图 |
| 适配器 | Adapter | 做 OrchestratorState ↔ LayerState 映射的中间层 |
| 条件边 | Conditional Edge | LangGraph 中根据 State 决定下一跳的边 |
| 中断恢复 | Interrupt/Resume | LangGraph 的 Human-in-the-Loop 机制 |
| 检查点 | Checkpoint | LangGraph 自动保存的中间状态，存入 PostgresSaver |
| 护栏 | Guardrail | LLM 调用前后的安全检查插件（7 个） |
| 熔断器 | Circuit Breaker | 连续失败后自动熔断的保护机制 |
| 故障转移 | Failover | Provider 不可用时自动切换 |
| 反思裁判 | ReflectionJudge | 知识检索后 LLM 判断检索质量并修正查询 |
| 倒数排名融合 | RRF | 多路检索结果融合算法（k=60） |
| 上下文压缩 | Context Compression | Token 超限时自动压缩历史消息 |
| 结构化输出 | Structured Output | PydanticOutputParser 让 LLM 输出 JSON Schema |
| 流式推送 | SSE | 服务端向客户端单向推送事件流 |
| 事件总线 | EventBus | 基于 asyncio.Queue 的 Pub/Sub 事件系统 |
| 并行扇出 | Send() Fan-Out | 将一个 State 同时发送给多个并行节点 |
| 线程ID | thread_id | LangGraph checkpoint 唯一标识，绑定 sessions 表 |
| 意图分类 | Intent Classify | 规则 + LLM 双保险判断用户输入类型 |
| 迭代决策 | Iteration Decision | 根据评分决定接受/重规划/重生成/人工介入 |
| 评分校准 | Score Calibration | 历史比对校准策略 |
| 多租户 | Multi-Tenant | 工作空间级别隔离，三级 Prompt 回退 |
| 数据脱敏 | Data Masking | LLM 调用前自动脱敏敏感数据 |

### 22.2 关键数字速查

| 指标 | 数值 |
|------|------|
| Agent Layer 数 | 4（Analysis 11 / Planning 14 / Generation 8 / Evaluation 9） |
| 主编排节点数 | 15 |
| 路由模块数 | 15 |
| 数据库表数 | 10 |
| 护栏插件数 | 7（pre_llm 3 + post_llm 4） |
| SSE 事件类型 | 已登记 14 + 代码未登记 5（chat.* ×4 + task.saved） |
| 评测维度数 | 10（含 completeness 无子节点） |
| 迭代最大轮数 | 3 |
| 评测通过分数 | ≥ 85 |
| 评测触发回退分数 | < 70 |
| 标准方案章节数 | 14 |
| JWT access/refresh 有效期 | 15 分钟 / 7 天 |
| SSE keepalive 间隔 | 30 秒 |
| EventBus queue maxsize | 128 |
| Failover 健康检测间隔 | 60 秒 |
| Provider 熔断阈值 / 恢复超时 | 3 次 / 30 秒 |
| Embedding 维度 | 1024（bge-large-zh-v1.5） |
| RRF k 值 | 60 |
| 文档上传最大大小 | 50 MB |
| 会话保留（free/pro/enterprise） | 30 / 180 / 不限 天 |
| 定时任务 | 图谱刷新 24h / 会话清理 1h / Web 同步 2h |
| 预算降级阈值 | 月预算 90% |
| 速率限制默认 | RPM 60 / TPM 100000 |

### 22.3 相关文档索引

```text
原始设计:        prd2tsd.prd.md
开发记录:        overview.md
技术栈声明:      tech-stack.yml
开发铁律:        DEVELOPMENT_GUIDE.md / VIBE_CODING_RULES.md
架构重构方案:    docs/deep-review-fix-plan.md
企业功能整改:    docs/enterprise-feature-revamp-plan.md
观测/评测/清理:  docs/plan-observability-eval-cleanup.md
各块设计:        docs/block-{A,B,C,D,E,F,G,H}-*.md
面试问答:        docs/interview-questions.md（本文档的面试部分已迁移至此）
```

> **文档结束** — v3.0 全链路架构文档，基于 2026-08-13 代码库真实状态。
> 覆盖：全模块（Block A-G + 观测/评测）+ 全链路（主线/对话/问答/文档分析/URL/断点恢复/历史消息/SSE/LLM 调用/可追踪/认证/知识图谱构建/检索/文档上传入图）。
> 面试相关章节见 `docs/interview-questions.md`。






