# PRD2TechSpec — 完整系统设计

## 一、系统全景架构

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               输入源（多格式扩展）                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐       │
│  │ 本地文件  │  │ ⭐⭐ CSV │  │ ⭐⭐ Web │  │  图片/   │  │ 搜索引擎回退     │       │
│  │ .md/.pdf │  │ .tsv    │  │ 页面/API │  │ 架构图   │  │ (本地无结果时)    │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘       │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   用户交互层                                            │
│           FastAPI (REST)                  Streamlit (Web UI)          CLI              │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                Agent Orchestrator (LangGraph)                          │
│                                                                                        │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐   │
│   │ Layer 1  │ → │ Layer 2  │ → │ Layer 3  │ → │ Layer 4  │   │   Evaluation     │   │
│   │Knowledge │   │Analysis  │   │Planning  │   │Generation│   │    System         │   │
│   │  Layer   │   │  Layer   │   │  Layer   │   │  Layer   │   │                   │   │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘   └──────────────────┘   │
│        │              │              │              │                                │
│        └──────────────┴──────────────┴──────────────┘                                │
│                                   ↑↓                                                  │
│                          ┌──────────────────┐                                        │
│                          │  Shared State    │                                        │
│                          │  (Orchestrator-  │                                        │
│                          │   State)         │                                        │
│                          └──────────────────┘                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                    基础设施层                                           │
│                                                                                        │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐               │
│  │   Neo4j (图数据库)  │  │  PostgreSQL+PGVector│  │   Redis (缓存/队列) │               │
│  │  知识图谱存储       │  │  向量+业务数据       │  │  Celery 任务队列    │               │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘               │
│                                                                                        │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐               │
│  │   MinIO (对象存储)  │  │   LLM Gateway      │  │   Prometheus +     │               │
│  │   PRD/方案文档+图片  │  │   多模型路由/限流   │  │   Grafana 监控     │               │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘               │
│                                                                                        │
│  ┌────────────────────┐  ┌────────────────────┐                                       │
│  │  ⭐ Kroki + Mermaid│  │  ⭐ CLIP 双塔模型   │     多模态 RAG 新增组件                │
│  │  图表渲染服务      │  │  视觉+文本Embedding │                                       │
│  └────────────────────┘  └────────────────────┘                                       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1.1 多租户与权限体系（企业级）

```
RBAC/ABAC 权限模型：
┌─────────────────────────────────────────────────────────┐
│                   认证层 (SSO/OAuth/OIDC)                 │
│     LDAP / 企业微信 / 飞书 / GitHub OAuth / Keycloak     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                    Token 管理 (JWT + Refresh)            │
│    access_token (15min) + refresh_token (7d) + 白名单   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                   权限中间件 (RBAC + ABAC)               │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ 超级管理员   │  │ 组织管理员   │  │ 项目管理员   │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         │                │                │           │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐    │
│  │ 架构师       │  │ 开发者       │  │ 查看者       │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│               资源级权限 (Resource-Level)                │
│                                                         │
│  - workspace:{id}:read         查看工作空间              │
│  - workspace:{id}:write        编辑工作空间              │
│  - prd:{id}:read               查看PRD                  │
│  - prd:{id}:write              编辑PRD                  │
│  - scheme:{id}:review          审核方案                  │
│  - knowledge:{id}:admin        管理知识库条目            │
│  - team:{id}:manage            管理团队成员              │
└─────────────────────────────────────────────────────────┘
```

### 1.1.1 数据模型

```sql
-- === 用户与认证 ===
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    display_name  VARCHAR(128) NOT NULL,
    avatar_url    TEXT,
    auth_provider VARCHAR(32) NOT NULL,  -- 'keycloak' / 'wecom' / 'ldap'
    auth_id       VARCHAR(255) NOT NULL, -- 外部认证系统的用户ID
    status        VARCHAR(16) DEFAULT 'active',  -- active / disabled / deleted
    preferences   JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(auth_provider, auth_id)
);

-- === 组织与工作空间 ===
CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(64) UNIQUE NOT NULL,
    plan        VARCHAR(32) DEFAULT 'free',  -- free / pro / enterprise
    settings    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE workspaces (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id   UUID REFERENCES organizations(id),
    name              VARCHAR(255) NOT NULL,
    slug              VARCHAR(64) NOT NULL,
    description       TEXT,
    knowledge_scope   VARCHAR(32) DEFAULT 'workspace',  -- workspace / org / global
    is_archived       BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, slug)
);

-- === 角色与权限 ===
CREATE TABLE roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    name            VARCHAR(64) NOT NULL,
    is_system       BOOLEAN DEFAULT FALSE,  -- 系统预置角色不可删除
    permissions     JSONB NOT NULL,  -- ["workspace:read", "prd:write", ...]
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE team_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID REFERENCES workspaces(id),
    user_id         UUID REFERENCES users(id),
    role_id         UUID REFERENCES roles(id),
    joined_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workspace_id, user_id)
);

-- === ⭐⭐ 新增：会话历史 ===
CREATE TABLE sessions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID REFERENCES workspaces(id),
    user_id           UUID REFERENCES users(id),
    title             VARCHAR(255) NOT NULL,                -- 会话标题（LLM自动生成或用户手动命名）
    session_type      VARCHAR(32) NOT NULL DEFAULT 'generate',  -- generate / review / knowledge_query / chat
    status            VARCHAR(16) DEFAULT 'active',         -- active / archived / deleted
    source_prd_id     UUID,                                 -- 关联的PRD文档ID（generate类型时）
    source_task_id    UUID,                                 -- 关联的任务ID
    summary           TEXT,                                 -- LLM生成的任务摘要
    message_count     INT DEFAULT 0,                        -- 消息总数
    token_count       INT DEFAULT 0,                        -- 消耗token总数
    cost_usd          DECIMAL(10,6) DEFAULT 0,              -- 消耗总成本（美元）
    rating            SMALLINT,                             -- 用户评分 1-5
    tags              TEXT[] DEFAULT '{}',                   -- 标签
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    last_message_at   TIMESTAMPTZ DEFAULT NOW(),            -- 最后一条消息时间
    deleted_at        TIMESTAMPTZ,                          -- 软删除时间
    UNIQUE(workspace_id, id)
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_workspace_id ON sessions(workspace_id);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX idx_sessions_last_message_at ON sessions(last_message_at DESC);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_tags ON sessions USING GIN(tags);

-- === ⭐⭐ 新增：会话消息 ===
CREATE TABLE session_messages (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID REFERENCES sessions(id) ON DELETE CASCADE,
    user_id           UUID REFERENCES users(id),
    role              VARCHAR(16) NOT NULL,                 -- user / assistant / system / tool
    content           TEXT NOT NULL,                         -- 消息内容（Markdown格式）
    content_type      VARCHAR(32) DEFAULT 'text',            -- text / image / file / code / mermaid
    attachments       JSONB DEFAULT '[]',                    -- 附件列表 [{type, url, name, size}]
    metadata          JSONB DEFAULT '{}',                    -- 额外元数据（模型、token消耗、延迟等）
    parent_message_id UUID,                                  -- 回复的消息ID（用于消息树）
    turn_index        INT NOT NULL,                          -- 对话轮次序号
    token_count       INT DEFAULT 0,                         -- 本消息消耗token数
    cost_usd          DECIMAL(10,6) DEFAULT 0,               -- 本消息消耗成本
    latency_ms        INT,                                   -- LLM响应延迟（毫秒）
    model_used        VARCHAR(64),                           -- 使用的模型名
    rating            SMALLINT,                              -- 单条消息评分
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, turn_index)
);

CREATE INDEX idx_messages_session_id ON session_messages(session_id);
CREATE INDEX idx_messages_created_at ON session_messages(created_at);
CREATE INDEX idx_messages_role ON session_messages(role);

-- === ⭐⭐ 新增：已上传文档管理 ===
CREATE TABLE uploaded_documents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID REFERENCES workspaces(id),
    user_id           UUID REFERENCES users(id),
    original_filename VARCHAR(255) NOT NULL,                -- 原始文件名
    storage_path      TEXT NOT NULL,                         -- MinIO/本地存储路径
    file_size         BIGINT NOT NULL,                       -- 文件大小（字节）
    file_type         VARCHAR(32) NOT NULL,                  -- md / pdf / docx / csv / tsv / png / jpg
    mime_type         VARCHAR(128),                          -- MIME类型
    file_hash         VARCHAR(64),                           -- SHA-256 文件哈希（去重用）
    title             VARCHAR(255),                          -- LLM提取的文档标题
    description       TEXT,                                  -- LLM生成的文档摘要
    page_count        INT,                                   -- PDF/文档页数
    word_count        INT,                                   -- 总字数
    source_url        TEXT,                                  -- 来源URL（网络资源导入时）
    
    -- 处理状态
    processing_status VARCHAR(32) DEFAULT 'pending',          -- pending / processing / indexed / failed
    processing_error  TEXT,                                   -- 处理失败原因
    indexed_at        TIMESTAMPTZ,                            -- 索引完成时间
    entity_count      INT DEFAULT 0,                          -- 提取的实体数
    relation_count    INT DEFAULT 0,                          -- 提取的关系数
    
    -- 关联信息
    session_id        UUID REFERENCES sessions(id),           -- 上传时所属会话
    task_id           UUID,                                   -- 关联的任务ID
    tags              TEXT[] DEFAULT '{}',
    is_deleted        BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    deleted_at        TIMESTAMPTZ
);

CREATE INDEX idx_documents_workspace_id ON uploaded_documents(workspace_id);
CREATE INDEX idx_documents_user_id ON uploaded_documents(user_id);
CREATE INDEX idx_documents_file_type ON uploaded_documents(file_type);
CREATE INDEX idx_documents_processing_status ON uploaded_documents(processing_status);
CREATE INDEX idx_documents_created_at ON uploaded_documents(created_at DESC);
CREATE INDEX idx_documents_tags ON uploaded_documents USING GIN(tags);
CREATE INDEX idx_documents_file_hash ON uploaded_documents(file_hash);
```

### 1.1.2 权限检查中间件

```python
class PermissionChecker:
    """权限检查中间件 - FastAPI Dependency"""
    
    async def __call__(self, 
                       request: Request,
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)) -> bool:
        # 1. 解析请求中的资源路径
        resource = self.parse_resource(request.url.path)
        
        # 2. 获取用户在该资源上的权限
        permissions = await self.get_user_permissions(user.id, resource.workspace_id)
        
        # 3. 检查操作所需权限
        required = self.get_required_permission(request.method, resource)
        if required not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f"缺少权限: {required}",
                headers={"X-Required-Permission": required}
            )
        
        # 4. ABAC 条件检查（可选）
        if not await self.check_abac_conditions(user, resource, request):
            raise HTTPException(status_code=403, detail="ABAC条件不满足")
        
        return True
```

### 1.1.3 OrchestratorState 扩展

```python
class OrchestratorState(TypedDict):
    # ... 原有字段 ...
    
    # --- 多租户上下文（新增） ---
    tenant_context: TenantContext
    workspace_id: str
    user_id: str
    user_role: str
    permissions: list[str]
    
    # --- ⭐⭐ 多模态上下文（新增） ---
    prd_images: list[str]                      # PRD中的图片路径列表（MinIO URI）
    query_image_path: Optional[str]            # 用户查询时上传的图片路径（以图搜图）
    image_chunks: list[ImageChunk]             # 从PRD图片提取的 ImageChunk 列表
    multimodal_results: list[ScoredImageChunk] # 多模态检索结果
    generated_diagrams: dict[str, GeneratedDiagram]  # 生成层输出的图表

class TenantContext(BaseModel):
    organization_id: str
    workspace_id: str
    knowledge_scope: str  # workspace / org / global
    settings: dict        # 工作空间级别配置（可覆盖全局）
```

---

## 1.2 LLM Gateway — 多模型管理与成本控制

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LLM Gateway                                  │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │  模型路由    │  │  成本追踪   │  │  响应缓存   │  │  流控     │ │
│  │  Route      │  │  Cost       │  │  Cache     │  │  Rate      │ │
│  │  Strategy   │  │  Tracking   │  │  (Semantic)│  │  Limiter   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘ │
│         │                │                │               │        │
│  ┌──────▼────────────────▼────────────────▼───────────────▼──────┐ │
│  │                    Provider 抽象层                              │ │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐     │ │
│  │  │OpenAI  │ │DeepSeek│ │  Claude│ │Gemini  │ │ 本地   │     │ │
│  │  │GPT-4o  │ │  V3    │ │Opus 4  │ │Pro 1.5│ │LLaMA   │     │ │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘     │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2.1 模型路由策略

```python
class ModelRouter:
    """
    根据任务类型自动选择最优模型
    策略：准确度要求高 → GPT-4o/Claude；成本敏感 → DeepSeek-V3
    """
    
    ROUTING_RULES = {
        # (layer, node) → (model, priority)
        "knowledge_retrieval":       ("deepseek-v3",   "cost"),     # 检索用便宜模型
        "analysis.requirement":      ("gpt-4o",        "quality"),  # 需求提取要精确
        "analysis.constraint":       ("deepseek-v3",   "cost"),
        "planning.pattern":          ("gpt-4o",        "quality"),  # 架构创意要强模型
        "planning.tech_stack":       ("deepseek-v3",   "cost"),
        "planning.self_check":       ("gpt-4o-mini",   "cost"),     # 自检用低成本
        "generation.section_writer": ("deepseek-v3",   "cost"),     # 写作量大用便宜的
        "generation.consistency":    ("gpt-4o-mini",   "cost"),
        "evaluation.scoring":        ("gpt-4o-mini",   "cost"),     # Judge用便宜模型
        "evaluation.security":       ("gpt-4o",        "quality"),  # 安全合规要严谨
    }
    
    def route(self, layer: str, node: str) -> str:
        key = f"{layer}.{node}"
        rule = self.ROUTING_RULES.get(key)
        if not rule:
            return "deepseek-v3"  # 默认
        return rule[0]
    
    def should_fallback(self, model: str, error: Exception) -> bool:
        """主模型失败时降级"""
        # 如果主模型是 GPT-4o，降到 DeepSeek-V3
        # 如果主模型是 DeepSeek-V3，降到 GPT-4o-mini
        fallback_chain = {
            "gpt-4o":        "deepseek-v3",
            "deepseek-v3":   "gpt-4o-mini",
            "gpt-4o-mini":   None,  # 最低了，不再降级
        }
        target = fallback_chain.get(model)
        return target if target else None
```

### 1.2.2 成本追踪与预算控制

```python
class CostTracker:
    """
    每次 LLM 调用记录成本
    数据写入 Prometheus + 审计日志
    """
    
    # 模型单价（每1M tokens，美元）
    PRICING = {
        "gpt-4o":        {"input": 5.00,  "output": 15.00},
        "gpt-4o-mini":   {"input": 0.15,  "output": 0.60},
        "deepseek-v3":   {"input": 0.27,  "output": 1.10},
        "claude-opus-4": {"input": 15.00, "output": 75.00},
    }
    
    @contextmanager
    def track(self, task_id: str, model: str, layer: str, node: str):
        """跟踪一次 LLM 调用"""
        start = time.time()
        start_tokens = self.get_token_usage()
        yield
        elapsed = time.time() - start
        end_tokens = self.get_token_usage()
        
        input_tokens = end_tokens.prompt - start_tokens.prompt
        output_tokens = end_tokens.completion - start_tokens.completion
        cost = self._calculate_cost(model, input_tokens, output_tokens)
        
        # 写入 Prometheus
        LLM_CALL_TOTAL.labels(model=model, layer=layer, node=node).inc()
        LLM_COST_TOTAL.labels(model=model).inc(cost)
        LLM_LATENCY.labels(model=model).observe(elapsed)
        LLM_TOKEN_USAGE.labels(model=model, type="input").inc(input_tokens)
        LLM_TOKEN_USAGE.labels(model=model, type="output").inc(output_tokens)
        
        # 写入审计日志
        logger.info("llm_call", extra={
            "task_id": task_id, "model": model,
            "layer": layer, "node": node,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost": round(cost, 6), "latency": round(elapsed, 3),
        })
        
        # 检查预算阈值
        self._check_budget(task_id, model, cost)


class BudgetController:
    """预算控制 - 防止单个任务/项目超出预算"""
    
    async def check_budget(self, workspace_id: str) -> bool:
        """检查工作空间是否还有剩余预算"""
        monthly_usage = await self.get_monthly_cost(workspace_id)
        budget = await self.get_workspace_budget(workspace_id)
        
        if monthly_usage > budget * 0.9:
            logger.warning(f"workspace {workspace_id} 预算使用超过90%")
            # 自动降级到便宜模型
            return self.switch_to_low_cost_model(workspace_id)
        
        return True
```

---

## 1.3 观测性体系（Observability）

### 1.3.1 分布式追踪

```python
# 使用 OpenTelemetry 全链路追踪
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

tracer = trace.get_tracer("prd2techspec")

class TracingMiddleware:
    """自动为每个 LangGraph 节点创建 Span"""
    
    def wrap_node(self, node_fn: Callable, node_name: str):
        @functools.wraps(node_fn)
        def traced_node(state: OrchestratorState) -> OrchestratorState:
            with tracer.start_as_current_span(
                f"layer.{node_name}",
                attributes={
                    "task_id": state.get("task_id", ""),
                    "workspace_id": state.get("workspace_id", ""),
                    "iteration": state.get("iteration_count", 0),
                }
            ) as span:
                try:
                    result = node_fn(state)
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    raise
        return traced_node
```

### 1.3.2 业务指标（Prometheus）

```python
# === Prometheus 指标定义 ===

# LLM 调用
LLM_CALL_TOTAL = Gauge("llm_calls_total", "LLM调用总数", ["model", "layer", "node"])
LLM_COST_TOTAL = Counter("llm_cost_total_usd", "LLM累计成本(美元)", ["model"])
LLM_LATENCY = Histogram("llm_latency_seconds", "LLM响应延迟", ["model"],
                        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0])
LLM_TOKEN_USAGE = Counter("llm_tokens_total", "Token消耗", ["model", "type"])

# 业务流程
TASKS_TOTAL = Counter("tasks_total", "任务总数", ["status"])
TASKS_DURATION = Histogram("tasks_duration_seconds", "任务耗时",
                           buckets=[10, 30, 60, 120, 300, 600, 1800])
TASK_ITERATIONS = Histogram("task_iterations", "任务迭代次数",
                            buckets=[1, 2, 3, 5, 10])

# 质量
QUALITY_SCORE = Gauge("quality_score", "方案质量评分", ["dimension"])
HUMAN_INTERVENTION_RATE = Gauge("human_intervention_rate", "人工介入率")
KNOWLEDGE_HIT_RATE = Gauge("knowledge_hit_rate", "知识检索命中率")

# 人工审核
REVIEW_PENDING = Gauge("review_pending_total", "待审核事项数")
REVIEW_APPROVAL_RATE = Gauge("review_approval_rate", "审核通过率")

# 系统
KNOWLEDGE_GRAPH_SIZE = Gauge("knowledge_graph_size", "知识图谱规模",
                             ["type"])  # entities / relations / text_units / communities / community_reports / claims
COMMUNITY_COUNT = Gauge("community_count", "社区数量", ["level"])
COMMUNITY_MODULARITY = Gauge("community_modularity", "社区模块度")

### 1.3.3 告警规则

```yaml
# prometheus_alerts.yml
groups:
  - name: prd2techspec
    rules:
      # === 成本告警 ===
      - alert: DailyCostAnomaly
        expr: increase(llm_cost_total_usd[24h]) > 50
        for: 1h
        labels: { severity: warning }
        annotations:
          summary: "日LLM成本异常: {{ $value }} 美元"
      
      # === 质量告警 ===
      - alert: QualityScoreDrop
        expr: avg_over_time(quality_score[1h]) < 70
        for: 5m
        labels: { severity: critical }
        annotations:
          summary: "方案质量评分低于70"
      
      - alert: KnowledgeHitRateDrop
        expr: knowledge_hit_rate < 0.5
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "知识图谱检索命中率低于50%"
      
      # === 性能告警 ===
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(llm_latency_seconds[5m])) > 15
        for: 5m
        labels: { severity: critical }
        annotations:
          summary: "LLM P95延迟超过15秒"
      
      # === 人工审核积压 ===
      - alert: ReviewBacklog
        expr: review_pending_total > 50
        for: 1h
        labels: { severity: warning }
        annotations:
          summary: "待审核事项超过50个，请及时处理"
```

---

### 1.3.4 LLM 可观测平台集成（LangFuse / LangSmith）

```python
class LLMObservability:
    """集成 LangFuse/LangSmith 记录每次LLM调用的完整上下文"""
    
    def __init__(self):
        self.client = LangFuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_HOST,
        )
    
    @contextmanager
    def trace_llm_call(self, task_id: str, model: str, 
                       layer: str, node: str, prompt: str):
        """记录完整 LLM 调用trace"""
        trace = self.client.trace(
            name=f"{layer}.{node}",
            input=prompt,
            metadata={
                "task_id": task_id,
                "model": model,
                "layer": layer,
                "node": node,
            }
        )
        generation = trace.generation(
            name=f"llm_call",
            model=model,
            input=prompt,
        )
        try:
            yield generation
        except Exception as e:
            generation.end(output=None, level="ERROR", 
                          status_message=str(e))
            raise
        finally:
            generation.end(output=generation.output)
```

---

## 二、Agent Orchestrator — 顶层编排

这是整个系统的**大脑**，用 LangGraph 的 `StateGraph` 实现。

### 2.1 全局状态定义

```python
class OrchestratorState(TypedDict):
    # --- 输入 ---
    prd_raw: str                          # PRD 原始内容
    prd_metadata: dict                     # 标题、作者、日期等
    prd_file_type: str                     # pdf/docx/md
    user_requirements: list[str]           # 用户额外要求
    
    # --- Layer 1: Knowledge ---
    knowledge_context: RetrievalContext    # Graph RAG 检索结果
    kg_entities: list[KGEntity]            # 提取的实体列表
    kg_relations: list[KGRelation]         # 提取的关系列表
    
    # --- Layer 2: Analysis ---
    analysis_result: AnalysisResult        # 结构化分析结果
    analysis_confidence: float              # 分析置信度
    
    # --- Layer 3: Planning ---
    planning_result: PlanningResult        # 架构规划结果
    architecture_diagram: str               # 架构图描述 (Mermaid)
    tech_stack_table: list[TechChoice]      # 技术栈选型表
    
    # --- Layer 4: Generation ---
    generation_result: GenerationResult    # 最终方案
    generated_docs: dict[str, str]          # {章节名: 内容}
    
    # --- Evaluation ---
    evaluation_report: EvaluationReport    # 评测报告
    quality_score: float                    # 综合质量评分
    
    # --- Control ---
    iteration_count: int                    # 迭代次数
    max_iterations: int                     # 最大迭代次数
    user_feedback: Optional[str]            # 人工反馈
    interrupt_points: list[str]            # 需要人工确认的点
    status: str                             # running/paused/complete/failed
```

### 2.2 主 Graph 结构

```python
orchestrator = StateGraph(OrchestratorState)

# 添加节点
orchestrator.add_node("knowledge_retrieval", KnowledgeRetrievalNode().run)
orchestrator.add_node("analysis", AnalysisAgent().run)
orchestrator.add_node("analysis_human_review", HumanReviewNode("analysis"))
orchestrator.add_node("planning", PlanningAgent().run)
orchestrator.add_node("planning_human_review", HumanReviewNode("planning"))
orchestrator.add_node("generation", GenerationAgent().run)
orchestrator.add_node("evaluation", EvaluationAgent().run)
orchestrator.add_node("iteration_decider", IterationDecider().run)
orchestrator.add_node("final_assembly", FinalAssemblyNode().run)

# 主流程
orchestrator.set_entry_point("knowledge_retrieval")
orchestrator.add_edge("knowledge_retrieval", "analysis")
orchestrator.add_conditional_edges(
    "analysis",
    needs_human_review,                      # 判断是否需要人工审核分析结果
    {True: "analysis_human_review", False: "planning"}
)
orchestrator.add_edge("analysis_human_review", "planning")
orchestrator.add_conditional_edges(
    "planning",
    needs_human_review,
    {True: "planning_human_review", False: "generation"}
)
orchestrator.add_edge("planning_human_review", "generation")
orchestrator.add_edge("generation", "evaluation")

# 迭代循环
orchestrator.add_conditional_edges(
    "evaluation",
    "iteration_decider",                     # 评估决策
    {
        "accept": "final_assembly",          # ✅ 通过
        "replan": "planning",                # 🔄 重新规划
        "regenerate": "generation",          # 🔄 重新生成
        "human_intervention": "analysis",    # 🧑 需要人工介入后重新分析
    }
)
orchestrator.add_edge("final_assembly", END)
```

### 2.3 Human-in-the-Loop 设计

```python
class HumanReviewNode:
    """
    人工审核节点 - 使用 LangGraph 的 interrupt 机制
    """
    def run(self, state: OrchestratorState) -> OrchestratorState:
        # 发送 interrupt，暂停 Graph 等待人工确认
        # LangGraph 的 interrupt 会让 action 等待，用户通过 API 提交反馈
        review_result = interrupt({
            "type": state.status,               # "analysis" / "planning"
            "data": state.analysis_result if state.status == "analysis" 
                    else state.planning_result,
            "questions": self._generate_review_questions(state),
        })
        
        # 人工返回的结果写入 state
        state.user_feedback = review_result.feedback
        if review_result.approved:
            state.status = "continue"
        else:
            state.status = "revise"
            # 记录人工修改建议
            state.interrupt_points.append(review_result.suggestions)
        
        return state
```

### 2.4 迭代决策逻辑

```python
class IterationDecider:
    def run(self, state: OrchestratorState) -> str:
        report = state.evaluation_report
        
        if state.iteration_count >= state.max_iterations:
            return "accept"  # 达到上限，强制接受
            
        if report.overall_score >= 85:
            return "accept"
        elif report.overall_score >= 70:
            # 预警状态，看具体哪个维度不达标
            if report.consistency < 0.7:
                return "regenerate"  # 一致性问题 → 重新生成
            elif report.feasibility < 0.7:
                return "replan"      # 可行性问题 → 重新规划
            else:
                return "accept"      # 小问题，接受
        else:
            # 严重不达标
            state.iteration_count += 1
            if report.has_analysis_error:
                return "human_intervention"  # 分析有问题，人工介入
            else:
                return "replan"              # 重新规划
```

---

## 三、Layer 1: Knowledge Layer — 完整设计

（已在上一轮详细给出，此处只补充与上层交互的接口）

### 3.1 暴露给 Orchestrator 的 Tool

```python
class KnowledgeRetrievalTool(BaseTool):
    """Knowledge Layer 对外唯一接口"""
    
    name = "knowledge_retrieval"
    description = "从知识图谱检索技术方案相关的知识上下文"
    
    args_schema: Type[BaseModel] = KnowledgeQuery
    
    def _run(self, query: str, search_mode: str = "auto",
             top_k: int = 10) -> RetrievalContext:
        """
        完整检索流水线（整合 Local + Global Search）：
        1. Intent Router → 确定搜索模式 (local/global/hybrid)
        2. Query Rewriter → 改写 3 条子查询
        3. Query Enricher → 实体链接扩展
        4. 按模式执行检索：
           - Local: 实体匹配 → 子图遍历 → TextUnit原文证据 → Claims上下文
           - Global: 社区报告匹配 → 层级选择 → 跨社区洞察 → LLM聚合
           - Hybrid: Local + Global 交替排列
        5. RRF Fusion → 融合
        6. Cross-encoder Re-rank → 重排
        7. Context Compression → 压缩
        8. Self-Evaluation → 质量自评
        """
        return self.pipeline.retrieve(query, search_mode, top_k)
    
    def run(self, query: str, search_mode: str = "auto",
            top_k: int = 10) -> RetrievalContext:
        return self._run(query, search_mode, top_k)
```

### 3.2 知识图谱构建 Pipeline

```python
class KnowledgeGraphBuilder:
    """
    知识图谱构建流水线 - 从原始文档构建知识图谱
    支持增量更新
    """
    def __init__(self):
        self.llm = get_llm()
        self.embed_model = get_embedding()
        self.graph_store = Neo4jGraphStore()
        self.vector_store = PGVectorStore()
    
    def build_from_documents(self, documents: list[Document]):
        # Phase 1: 文档处理
        chunks = self.chunk_documents(documents)
        
        # Phase 2: 实体提取 (LLM)
        entities = self.extract_entities(chunks)
        
        # Phase 3: 关系提取 (LLM)
        relations = self.extract_relations(entities, chunks)
        
        # Phase 4: 写入图数据库
        self.graph_store.upsert_entities(entities)
        self.graph_store.upsert_relations(relations)
        
        # Phase 5: 构建向量索引 (LlamaIndex)
        index = PropertyGraphIndex.from_documents(
            documents,
            llm=self.llm,
            embed_model=self.embed_model,
            kg_store=self.graph_store,
            show_progress=True,
        )
        # Phase 6: 持久化
        index.storage_context.persist("./storage/kg_index")
    
    def extract_entities(self, chunks: list[Document]) -> list[KGEntity]:
        """实体提取 - 使用 LLM + 预设 Schema"""
        EXTRACT_PROMPT = """
        你是一个技术文档实体提取专家。从以下文档中提取技术相关实体。
        
        实体类型包括：
        - TechStack: 技术栈（Spring Boot, Redis, PostgreSQL...）
        - Component: 组件名（用户模块、订单服务...）
        - ArchitecturePattern: 架构模式（微服务、事件驱动...）
        - Constraint: 约束条件（高可用、低延迟...）
        - Concept: 抽象概念（CAP定理、DDD...）
        
        文档内容：
        {chunk}
        
        输出 JSON 列表：[{{"name": "", "type": "", "description": ""}}]
        """
        entities = []
        for chunk in chunks:
            result = self.llm.complete(EXTRACT_PROMPT.format(chunk=chunk.text))
            entities.extend(parse_entities(result.text))
        return self.deduplicate_entities(entities)
    
    def extract_relations(self, entities: list[KGEntity], 
                         chunks: list[Document]) -> list[KGRelation]:
        """关系提取 - 两两判断实体间关系"""
        RELATION_PROMPT = """
        判断以下两个技术实体之间的关系类型：
        
        实体A: {entity_a}
        实体B: {entity_b}
        
        关系类型：
        - depends_on: A依赖B
        - implements: A实现B
        - recommends: A推荐B
        - conflicts_with: A与B冲突
        - alternative_to: A是B的替代方案
        - part_of: A是B的一部分
        
        文档上下文（用于辅助判断）：
        {context}
        
        如果有关系，输出 JSON {{"relation": "depends_on", "reason": ""}}
        如果没有关系，输出 {{"relation": null}}
        """
        relations = []
        for a, b in combinations(entities, 2):
            context = self.find_relevant_chunk(a, b, chunks)
            result = self.llm.complete(RELATION_PROMPT.format(
                entity_a=a.name, entity_b=b.name, context=context
            ))
            relation = parse_relation(result.text)
            if relation:
                relations.append(KGRelation(
                    source=a.id, target=b.id,
                    type=relation.relation, reason=relation.reason
                ))
        return relations
```

#### 3.2.1 文档分块与 TextUnit 中间层

```
文档分块策略全景：
┌─────────────────────────────────────────────────────────────────────────┐
│                          Document → Chunks → TextUnits                    │
│                                                                          │
│  原始文档                         TextUnit（文本单元）                     │
│  ┌──────────┐     ┌──────────┐     ┌──────────────────────────┐         │
│  │ PRD.md   │────→│ Chunk 1  │────→│ TU-001: "用户认证模块..." │         │
│  │          │     │ (800 tok)│     │   entities: [用户服务]     │         │
│  │          │     ├──────────┤     │   section: §3.1.2          │         │
│  │          │     │ Chunk 2  │     ├──────────────────────────┤         │
│  │          │     │ (800 tok)│     │ TU-002: "JWT + OAuth2..." │         │
│  │          │     ├──────────┤     │   entities: [JWT, OAuth2]  │         │
│  │          │     │ Chunk 3  │     │   section: §3.1.2          │         │
│  │          │     │ ...      │     └──────────────────────────┘         │
│  └──────────┘     └──────────┘                                           │
│                                                                          │
│  TextUnit 是 Chunk 与 Entity/Relation 之间的桥梁：                        │
│  - 每个 TextUnit 携带：原文片段 + 关联的实体列表 + 来源章节/页码            │
│  - 检索时可直接引用 TextUnit 原文作为证据                                  │
│  - 社区摘要生成时以 TextUnit 为最小语义单元                                │
└─────────────────────────────────────────────────────────────────────────┘
```

**分块策略 — 三级多粒度设计：**

```python
class MultiGranularityChunker:
    """
    多粒度分块策略 — 支持 Sentence / Paragraph / Section 三级
    不同粒度服务于不同检索场景：
    - Sentence 级：精确匹配、实体消歧
    - Paragraph 级：Local Search 上下文证据
    - Section 级：Global Search 社区摘要输入
    """
    
    # 三级粒度配置
    GRANULARITIES = {
        "sentence": {
            "chunk_size": 256,        # tokens
            "chunk_overlap": 64,
            "separator": r'(?<=[。！？\n])(?=[^\s])',  # 句子边界
            "min_chunk_size": 80,
            "use_for": ["entity_extraction", "entity_disambiguation"],
        },
        "paragraph": {
            "chunk_size": 800,
            "chunk_overlap": 200,
            "separator": r'\n\n+',                    # 段落边界
            "min_chunk_size": 200,
            "use_for": ["relation_extraction", "local_search", "text_unit_source"],
        },
        "section": {
            "chunk_size": 3000,
            "chunk_overlap": 500,
            "separator": r'^#{1,3}\s',               # Markdown 标题边界
            "min_chunk_size": 500,
            "use_for": ["community_summary", "global_search", "outline"],
        },
    }
    
    def chunk(self, documents: list[Document]) -> MultiGranularityChunks:
        """
        返回三级粒度的分块结果
        Chunk 之间通过 parent_id 形成层级关系：
        Sentence ⊂ Paragraph ⊂ Section
        """
        result = MultiGranularityChunks()
        
        for doc in documents:
            # 1. Section 级切分（按 Markdown 标题结构）
            sections = self._split_by_sections(doc)
            for sec in sections:
                sec_chunk = self._create_chunk(sec, "section", doc)
                
                # 2. 每个 Section 内按段落切分
                paragraphs = self._split_by_paragraphs(sec)
                for para in paragraphs:
                    para_chunk = self._create_chunk(
                        para, "paragraph", doc,
                        parent_id=sec_chunk.id
                    )
                    
                    # 3. 每个 Paragraph 内按句子切分
                    sentences = self._split_by_sentences(para)
                    for sent in sentences:
                        sent_chunk = self._create_chunk(
                            sent, "sentence", doc,
                            parent_id=para_chunk.id
                        )
                        result.add("sentence", sent_chunk)
                    
                    result.add("paragraph", para_chunk)
                
                result.add("section", sec_chunk)
        
        return result
    
    def _create_chunk(self, text: str, granularity: str,
                      doc: Document, parent_id: str = None) -> Chunk:
        """创建 Chunk 并提取元数据"""
        return Chunk(
            id=str(uuid4()),
            text=text,
            granularity=granularity,
            parent_id=parent_id,                          # 层级关系
            metadata={
                "doc_id": doc.id,
                "doc_title": doc.metadata.get("title", ""),
                "section_title": self._extract_section_title(text),
                "section_path": self._extract_section_path(text),  # "§3.1.2"
                "page_number": doc.metadata.get("page_number"),
                "token_count": count_tokens(text),
                "language": detect_language(text),        # zh/en/mix
            },
        )
```

**TextUnit — 连接 Chunk 与 Graph 的中间层：**

```python
class TextUnitBuilder:
    """
    TextUnit 是 Graph RAG 中的关键中间层：
    1. 追踪每个实体/关系从哪段原文提取的（证据链）
    2. Local Search 时作为实体的可信原文上下文
    3. Community Report 生成时的输入单元
    4. Covariate/Claims 提取时附着的载体
    
    TextUnit 与 Entity 之间是多对多关系：
    - 一个 TextUnit 可包含多个 Entity
    - 一个 Entity 可出现在多个 TextUnit 中
    """
    
    def build_from_chunks(self, chunks: list[Chunk],
                          entities: list[KGEntity],
                          relations: list[KGRelation]) -> list[TextUnit]:
        """从 paragraph 级 Chunk 构建 TextUnit"""
        text_units = []
        
        for chunk in chunks:
            if chunk.granularity != "paragraph":
                continue  # TextUnit 以 paragraph 粒度为单位
            
            # 1. 找出与该 chunk 相关的实体
            linked_entities = [
                e for e in entities
                if self._entity_in_chunk(e, chunk)
            ]
            
            # 2. 找出与该 chunk 相关的关系
            linked_relations = [
                r for r in relations
                if self._relation_in_chunk(r, chunk, linked_entities)
            ]
            
            # 3. 生成 TextUnit（包含原文 + 结构化信息）
            text_unit = TextUnit(
                id=f"TU-{str(uuid4())[:8]}",
                chunk_id=chunk.id,
                text=chunk.text,                          # 原始文本片段
                entities=[e.id for e in linked_entities],  # 关联实体 ID
                relations=[r.id for r in linked_relations],# 关联关系 ID
                metadata={
                    "section_path": chunk.metadata.get("section_path"),
                    "token_count": chunk.metadata.get("token_count"),
                    "entity_count": len(linked_entities),
                },
                # 实体 embedding 均值（用于 TextUnit 级语义匹配）
                embedding=self._compute_textunit_embedding(
                    chunk.text, linked_entities
                ),
            )
            text_units.append(text_unit)
        
        return text_units
    
    def _entity_in_chunk(self, entity: KGEntity, chunk: Chunk) -> bool:
        """判断实体是否出现在 chunk 中"""
        # 精确匹配 + 别名匹配
        names = [entity.name] + entity.aliases
        return any(name.lower() in chunk.text.lower() for name in names)
```

#### 3.2.2 社区检测与摘要（Community Detection & Summarization）

```
社区检测流程：
┌────────────────────────────────────────────────────────────────────────────┐
│              实体关系图 ──→ 社区检测 ──→ 社区摘要                          │
│                                                                           │
│  ┌───────┐  depends_on  ┌───────────┐                                     │
│  │用户服务├─────────────→│ 认证中心   │    Leiden 算法                       │
│  └───┬───┘              └─────┬─────┘    ↓                                │
│      │ depends_on             │ depends_on    ┌───────────────────┐       │
│      ▼                        ▼               │ Community 1 (Level 0)      │
│  ┌───────┐              ┌───────────┐         │ "认证域"                    │
│  │ 数据库 │              │ Redis缓存 │         │  用户服务, 认证中心,        │
│  └───┬───┘              └───────────┘         │  Redis缓存, 数据库         │
│      │                                        └───────────┬───────────────┘
│      │ relates                                  │
│      ▼                                          │
│  ┌───────────┐  conflicts  ┌───────────┐        ▼
│  │ 消息队列   ├────────────→│ 文件存储   │    ┌───────────────────┐
│  └───────────┘              └───────────┘    │ Community 2 (Level 0)      │
│                                              │ "基础设施域"               │
│   社区层级关系：                               │  消息队列, 文件存储        │
│   Level 0 → Level 1 → Level 2               └───────────┬───────────────┘
│   (细粒度)              (粗粒度)                          │
│                                              ┌───────────▼───────────────┐
│                                              │ Community 3 (Level 1)      │
│                                              │ "整体平台" (合并 C1+C2)    │
│                                              └───────────────────────────┘
└────────────────────────────────────────────────────────────────────────────┘
```

```python
class CommunityDetector:
    """
    使用 Leiden 算法进行社区检测
    Leiden 比 Louvain 更快且保证社区连通性
    
    核心流程：
    1. 从 Neo4j 导出图结构 → NetworkX
    2. 运行 Leiden 多层级社区检测
    3. 对每层每个社区生成摘要报告（Community Report）
    4. 社区报告写入向量库用于 Global Search
    """
    
    def detect(self, graph: NetworkXGraph) -> CommunityHierarchy:
        """
        多层级社区检测
        返回 Level 0 ~ Level N 的社区层级树
        """
        import igraph as ig
        from leidenalg import find_partition
        
        # 1. 转换为 igraph
        g = self._to_igraph(graph)
        
        # 2. 运行 Leiden 多级分区
        partition = find_partition(
            g,
            leidenalg.ModularityVertexPartition,
            n_iterations=10,
            seed=42,
        )
        
        # 3. 构建社区层级树
        communities = []
        for level in range(partition.level_count()):
            level_comms = self._extract_level_communities(
                graph, partition, level
            )
            communities.extend(level_comms)
        
        return CommunityHierarchy(
            communities=communities,
            level_count=partition.level_count(),
            modularity=partition.quality(),
        )
    
    def _extract_level_communities(self, graph, partition,
                                   level: int) -> list[Community]:
        """提取某一层级的社区"""
        communities = []
        member_map = partition.membership(level)  # {node_idx: community_id}
        
        # 按 community_id 分组
        comm_groups = defaultdict(list)
        for node_idx, comm_id in enumerate(member_map):
            comm_groups[comm_id].append(node_idx)
        
        for comm_id, node_indices in comm_groups.items():
            entity_ids = [graph.node_ids[i] for i in node_indices]
            communities.append(Community(
                id=f"COMM-L{level}-{comm_id}",
                level=level,
                entity_ids=entity_ids,
                entity_count=len(entity_ids),
                # 社区内关系：只保留两端都在社区内的边
                internal_edges=[
                    e for e in graph.edges
                    if e.source in entity_ids and e.target in entity_ids
                ],
                # 社区间关系：一端在社区内、一端在外
                external_edges=[
                    e for e in graph.edges
                    if (e.source in entity_ids) != (e.target in entity_ids)
                ],
            ))
        
        return communities
```

**社区摘要生成（Community Report）：**

```python
class CommunityReportGenerator:
    """
    为每个社区生成结构化摘要报告
    Community Report 是 Global Search 的核心数据源
    
    报告内容：
    1. 社区主题概述
    2. 核心实体及职责
    3. 内部关系总结（关键依赖/数据流）
    4. 外部联系（与相邻社区的交互）
    5. 关键决策与权衡
    """
    
    REPORT_PROMPT = """
    你是一个技术架构分析专家。以下是知识图谱中的一个社区（一组紧密相关的技术实体）。
    
    ## 社区信息
    社区层级：Level {level}
    实体数量：{entity_count}
    
    ## 核心实体
    {entities}
    
    ## 内部关系
    {internal_relations}
    
    ## 外部关系（跨社区交互）
    {external_relations}
    
    ## 原始上下文（TextUnit 证据）
    {text_unit_contexts}
    
    请生成一份社区摘要报告，包含：
    
    1. **社区主题** (title)：用一句话概括这个社区的核心关注点
    2. **总体概述** (summary)：2-4段话描述该社区的职能和设计思路
    3. **关键实体** (key_entities)：挑出 3-5 个最重要的实体并说明其角色
    4. **内部架构** (internal_architecture)：描述实体间的核心交互模式/数据流
    5. **外部接口** (external_interfaces)：列出与相邻社区的关键交互
    6. **发现洞察** (findings)：从原始上下文中提取的重要架构决策、权衡或约束
    
    输出 JSON 格式：
    {{
        "title": "认证与用户管理域",
        "summary": "该社区负责用户身份认证与会话管理...",
        "key_entities": [
            {{"name": "认证中心", "role": "统一认证入口，处理OAuth2/JWT签发"}},
            {{"name": "用户服务", "role": "用户CRUD与画像管理"}}
        ],
        "internal_architecture": "用户服务依赖认证中心进行Token验证，通过Redis缓存会话...",
        "external_interfaces": [
            {{"target_community": "订单域", "interaction": "通过gRPC提供用户身份校验", "protocol": "gRPC"}}
        ],
        "findings": [
            {{"type": "decision", "content": "选择JWT而非Session方案以减少服务状态"}},
            {{"type": "constraint", "content": "Token有效期15分钟，由安全合规约束决定"}}
        ],
        "rating": 4   // 1-5，社区结构的清晰度和内聚度评分
    }}
    """
    
    def generate_all_reports(self, communities: list[Community],
                             text_units: list[TextUnit]) -> list[CommunityReport]:
        """为所有社区生成摘要报告"""
        reports = []
        
        for comm in communities:
            # 收集该社区的 TextUnit 作为证据
            relevant_tus = [
                tu for tu in text_units
                if any(eid in comm.entity_ids for eid in tu.entities)
            ]
            
            # 构建 prompt 输入
            entities_info = self._format_entities(comm.entity_ids)
            internal_info = self._format_relations(comm.internal_edges)
            external_info = self._format_relations(comm.external_edges)
            tu_contexts = "\n---\n".join([
                f"[{tu.metadata.get('section_path', '')}] {tu.text[:500]}"
                for tu in relevant_tus[:10]  # 最多取10个相关TextUnit
            ])
            
            result = self.llm.complete(
                self.REPORT_PROMPT.format(
                    level=comm.level,
                    entity_count=comm.entity_count,
                    entities=entities_info,
                    internal_relations=internal_info,
                    external_relations=external_info,
                    text_unit_contexts=tu_contexts,
                ),
                response_format={"type": "json_object"}
            )
            
            report_data = json.loads(result.text)
            report = CommunityReport(
                id=f"CR-{comm.id}",
                community_id=comm.id,
                level=comm.level,
                **report_data,
                # 向量化报告内容，用于 Global Search 语义匹配
                embedding=self.embed_model.embed(
                    f"{report_data['title']}\n{report_data['summary']}"
                ),
            )
            reports.append(report)
        
        return reports
    
    def store_reports(self, reports: list[CommunityReport]):
        """将报告写入 PGVector 用于 Global Search"""
        for report in reports:
            self.vector_store.upsert(
                id=report.id,
                text=f"# {report.title}\n\n{report.summary}",
                embedding=report.embedding,
                metadata={
                    "community_id": report.community_id,
                    "level": report.level,
                    "entity_count": len(report.key_entities),
                    "rating": report.rating,
                    "findings": json.dumps(report.findings),
                },
            )
```

#### 3.2.3 图谱丰富化（Graph Enrichment）

**Claims/Covariates 提取：**

```python
class ClaimsExtractor:
    """
    从 TextUnit 中提取声明性断言（Claims）
    
    Claim 是与时间相关的、可能随时间变化的声明：
    - "MySQL 8.0 比 PostgreSQL 15 在大表扫描场景下快 30%"  ← 可能过时
    - "团队选择 Go 是因为需要更好的并发性能"             ← 决策声明
    - "Redis 集群预期承载 10万 QPS"                      ← 性能预期
    
    Claims 的用途：
    1. 补充 Entity 之间的隐式关系
    2. 提供决策依据（Local Search 时展示"为什么选这个技术"）
    3. 知识老化检测（Claims 的时间戳可用于判断信息是否过时）
    """
    
    CLAIMS_PROMPT = """
    从以下技术文档片段中提取声明性断言（Claims）。
    
    文本单元：
    {text_unit}
    
    关联实体：{linked_entities}
    
    Claim 类型：
    - comparison: A 与 B 的对比性声明 ("X 比 Y 快")
    - decision: 技术选型决策及理由 ("选择了 X 因为 Y")
    - specification: 规格/指标声明 ("QPS 需要达到 10000")
    - constraint: 约束声明 ("必须兼容 JDK 17+")
    - prediction: 预测/预期 ("预计 Q3 上线")
    - fact: 事实性声明 ("X 依赖 Y 的 v3.2 版本")
    
    输出 JSON 列表：
    [{
        "subject": "Redis Cluster",
        "claim_type": "specification",
        "claim": "Redis Cluster 需要支持 10万 QPS 读操作",
        "object": null,
        "confidence": 0.9,
        "source_textunit": "TU-xxx",
        "time_validity": "2026-Q3",   // 如果声明有时效性
        "subject_entity_id": "xxx",    // subject 对应的 Entity ID
        "object_entity_id": null,      // object 对应的 Entity ID（如有）
        "evidence": "PRD 第3.2节明确要求"  // 找到的证据文本
    }]
    
    如果没有声明性断言，输出空列表 []。
    """
    
    def extract(self, text_units: list[TextUnit],
                entities: list[KGEntity]) -> list[Claim]:
        """从所有 TextUnit 提取 Claims"""
        all_claims = []
        
        for tu in text_units:
            linked = [e for e in entities if e.id in tu.entities]
            
            result = self.llm.complete(
                self.CLAIMS_PROMPT.format(
                    text_unit=tu.text[:2000],
                    linked_entities=", ".join(
                        [f"{e.name}({e.type})" for e in linked]
                    ),
                ),
                response_format={"type": "json_object"}
            )
            claims_data = json.loads(result.text)
            
            for c in claims_data:
                claim = Claim(
                    id=f"CL-{str(uuid4())[:8]}",
                    textunit_id=tu.id,
                    **c,
                    extracted_at=datetime.utcnow(),
                )
                all_claims.append(claim)
        
        return all_claims
    
    def store_claims(self, claims: list[Claim]):
        """Claims 写入 Neo4j 和 PGVector"""
        for claim in claims:
            # 写入 Neo4j 作为实体间边缘信息
            if claim.subject_entity_id:
                self.graph_store.attach_claim(
                    entity_id=claim.subject_entity_id,
                    claim=claim,
                )
            # 向量化存入 PGVector（可用于检索"为什么选择了X"类问题）
            self.vector_store.upsert(
                id=claim.id,
                text=claim.claim,
                embedding=self.embed_model.embed(claim.claim),
                metadata={
                    "claim_type": claim.claim_type,
                    "subject": claim.subject,
                    "textunit_id": claim.textunit_id,
                    "time_validity": claim.time_validity,
                },
            )
```

**实体 Embedding 生成：**

```python
class EntityEmbedder:
    """
    为每个实体生成 Embedding
    用于实体级别语义匹配和消歧
    
    实体 Embedding 来源：
    1. 实体名称 + 描述 的 Embedding
    2. 实体所在 TextUnit 的 Embedding 加权平均
    3. 关联 Claims 的 Embedding 加权平均
    
    用途：
    - 实体消歧（同名的 Spring 是指框架还是弹簧？）
    - 实体链接（Query Enricher 中匹配用户查询中的实体）
    - 相似实体推荐（"看看类似的架构模式"）
    """
    
    def embed_entity(self, entity: KGEntity,
                     text_units: list[TextUnit],
                     claims: list[Claim]) -> np.ndarray:
        """
        生成实体的多源融合 Embedding
        """
        embeddings = []
        weights = []
        
        # 1. 实体本身（名称+描述） — 权重最高
        entity_text = f"{entity.name}: {entity.description}"
        embeddings.append(self.embed_model.embed(entity_text))
        weights.append(1.0)
        
        # 2. 实体所在 TextUnit 的 Embedding 加权
        linked_tus = [tu for tu in text_units if entity.id in tu.entities]
        if linked_tus:
            tu_embeddings = [tu.embedding for tu in linked_tus if tu.embedding]
            if tu_embeddings:
                embeddings.append(np.mean(tu_embeddings, axis=0))
                weights.append(0.5)
        
        # 3. 关联 Claims 的 Embedding 加权
        linked_claims = [
            c for c in claims if c.subject_entity_id == entity.id
        ]
        if linked_claims:
            claim_embeddings = [
                self.embed_model.embed(c.claim) for c in linked_claims[:5]
            ]
            embeddings.append(np.mean(claim_embeddings, axis=0))
            weights.append(0.3)
        
        # 加权平均
        weights = np.array(weights) / sum(weights)
        fused = np.average(embeddings, axis=0, weights=weights)
        
        # 写入 Neo4j 实体属性
        self.graph_store.update_entity(
            entity.id,
            {"embedding": fused.tolist()}
        )
        
        return fused
```

#### 3.2.4 构建 Pipeline 完整版（整合所有新增阶段）

```python
class KnowledgeGraphBuilder:  # complete version
    """知识图谱构建流水线 — 完整版"""
    
    def build_from_documents(self, documents: list[Document]):
        """完整构建流水线"""
        
        # === Phase 0: 文档分块（多粒度） ===
        self.chunker = MultiGranularityChunker()
        multi_chunks = self.chunker.chunk(documents)
        # 实体/关系提取用 paragraph 级
        chunks = multi_chunks.get("paragraph")
        
        # === Phase 1: 实体提取 ===
        entities = self.extract_entities(chunks)
        entities = self.entity_resolver.resolve_batch(entities)
        
        # === Phase 2: 关系提取 ===
        relations = self.extract_relations(entities, chunks)
        
        # === Phase 3: TextUnit 构建（中间层） ===
        self.tu_builder = TextUnitBuilder()
        text_units = self.tu_builder.build_from_chunks(
            chunks, entities, relations
        )
        
        # === Phase 4: 写入图数据库（实体 + 关系 + TextUnit 引用） ===
        self.graph_store.upsert_entities(entities)
        self.graph_store.upsert_relations(relations)
        self.graph_store.upsert_text_units(text_units)     # TextUnit → Neo4j
        
        # === Phase 5: Claims 提取 ===
        self.claims_extractor = ClaimsExtractor()
        claims = self.claims_extractor.extract(text_units, entities)
        self.claims_extractor.store_claims(claims)
        
        # === Phase 6: 实体 Embedding ===
        self.entity_embedder = EntityEmbedder()
        for entity in entities:
            self.entity_embedder.embed_entity(entity, text_units, claims)
        
        # === Phase 7: 社区检测 ===
        self.community_detector = CommunityDetector()
        graph_nx = self.graph_store.to_networkx()
        hierarchy = self.community_detector.detect(graph_nx)
        
        # === Phase 8: 社区摘要生成 ===
        self.report_generator = CommunityReportGenerator()
        reports = self.report_generator.generate_all_reports(
            hierarchy.communities, text_units
        )
        self.report_generator.store_reports(reports)
        
        # === Phase 9: 向量索引 ===
        index = PropertyGraphIndex.from_documents(
            documents,
            llm=self.llm,
            embed_model=self.embed_model,
            kg_store=self.graph_store,
            show_progress=True,
        )
        
        # === Phase 10: 持久化 ===
        index.storage_context.persist("./storage/kg_index")
        
        # === 构建统计 ===
        return BuildStats(
            entities=len(entities),
            relations=len(relations),
            text_units=len(text_units),
            claims=len(claims),
            communities=len(hierarchy.communities),
            community_reports=len(reports),
            hierarchy_levels=hierarchy.level_count,
            modularity=hierarchy.modularity,
        )
```

### 3.3 知识图谱 Schema — 完整定义

```
节点类型 (Node Labels):
├── TechStack          # 技术栈（带 category: backend/frontend/db/mq/cache...）
├── Component          # 系统组件
├── ArchitecturePattern # 架构模式
├── Constraint         # 约束条件（带 type: performance/security/scalability...）
├── Concept            # 技术概念
├── Project            # 历史项目/方案
├── BestPractice       # 最佳实践
├── Risk               # 已知风险
├── Domain             # 业务领域
├── TextUnit           # ⭐ 文本单元（Chunk与Entity的桥梁，带原文+关联实体+Embedding）
├── Community          # ⭐ 社区（Leiden算法检测的实体聚类，含层级level）
├── CommunityReport    # ⭐ 社区摘要报告（含主题/概述/关键实体/洞察/向量）
├── Claim              # ⭐ 声明性断言（对比/决策/规格/约束/预测，带时间戳）
├── ImageChunk         # ⭐⭐ 多模态图片单元（视觉Embedding + 文本Embedding 双向量，支持以图搜图）
├── DiagramTemplate    # ⭐⭐ 图表生成模板（Mermaid/PlantUML 模板，供生成层渲染架构图）

关系类型 (Relationship Types):
├── depicts            # ⭐⭐ ImageChunk 描述了某个实体/组件（多模态溯源）
├── visualized_by      # ⭐⭐ 实体被某张 ImageChunk 可视化
├── depends_on         # A 依赖于 B
├── implements         # A 实现了 B（概念/模式）
├── recommends         # A 推荐使用 B
├── conflicts_with     # A 与 B 不兼容/冲突
├── alternative_to     # A 是 B 的替代方案
├── part_of            # A 是 B 的组成部分
├── used_by            # A 被 B 使用（反向依赖）
├── satisfies          # A 满足约束条件 B
├── has_risk           # A 有风险 B
├── similar_to         # A 与 B 相似（语义相似）
├── predecessor_of     # A 是 B 的前置条件
├── references         # A 引用了 B（文档引用）
├── extracted_from     # ⭐ Entity 提取自 TextUnit
├── belongs_to         # ⭐ Entity 属于 Community
├── has_report         # ⭐ Community 有 CommunityReport
├── has_claim          # ⭐ Entity 有 Claim
├── claims_about       # ⭐ Claim 关于 Entity A 和 Entity B

节点属性:

# === 原有节点 ===
TechStack:
{
  "name": "Spring Boot",
  "type": "TechStack",
  "category": "backend_framework",
  "version": "3.2.0",
  "description": "Spring 生态的微服务开发框架",
  "tags": ["java", "微服务", "web"],
  "pros": ["生态丰富", "社区活跃"],
  "cons": ["启动慢", "内存占用高"],
  "confidence": 0.95,
  "source": "历史方案-电商平台v2",
  "embedding": [0.023, -0.15, ...],  # ⭐ 实体多源融合Embedding
  "created_at": "2026-01-15",
  "updated_at": "2026-06-20"
}

# === ⭐ 新增节点 ===
TextUnit:
{
  "id": "TU-a1b2c3d4",
  "chunk_id": "chunk-xxx",
  "text": "用户认证模块采用JWT + OAuth2方案...",
  "entities": ["entity-uuid-1", "entity-uuid-2"],
  "relations": ["rel-uuid-1"],
  "metadata": {
    "section_path": "§3.1.2 认证设计",
    "token_count": 245,
    "entity_count": 3
  },
  "embedding": [0.012, -0.034, ...]   # TextUnit级Embedding
}

Community:
{
  "id": "COMM-L0-3",
  "level": 0,                           # 社区层级（0=最细粒度）
  "entity_ids": ["uuid-1", "uuid-2"],
  "entity_count": 5,
  "internal_edge_count": 8,
  "external_edge_count": 3,
  "modularity_contribution": 0.12       # 该社区对整体modularity的贡献
}

CommunityReport:
{
  "id": "CR-COMM-L0-3",
  "community_id": "COMM-L0-3",
  "level": 0,
  "title": "认证与用户管理域",
  "summary": "该社区负责用户身份认证与会话管理...",
  "key_entities": [{"name": "认证中心", "role": "..."}],
  "internal_architecture": "用户服务依赖认证中心...",
  "external_interfaces": [{"target_community": "订单域", ...}],
  "findings": [{"type": "decision", "content": "..."}],
  "rating": 4,
  "embedding": [0.056, -0.012, ...]    # 用于Global Search语义匹配
}

Claim:
{
  "id": "CL-a1b2c3d4",
  "subject": "Redis Cluster",
  "claim_type": "specification",
  "claim": "Redis Cluster 需要支持 10万 QPS 读操作",
  "object": null,
  "confidence": 0.9,
  "source_textunit": "TU-xxx",
  "time_validity": "2026-Q3",
  "subject_entity_id": "entity-uuid-5",
  "extracted_at": "2026-07-15T10:30:00Z"
}

# === ⭐⭐ 新增多模态节点 ===
ImageChunk:
{
  "id": "IMG-a1b2c3d4",
  "image_path": "minio://prd2tsd/uploads/arch-v2.png",
  "thumbnail_path": "minio://prd2tsd/thumbnails/arch-v2_thumb.png",
  "description": "整体采用微服务架构，前端通过API网关接入...",
  "diagram_type": "architecture",      # architecture / flow / deployment / ui_wireframe / er_diagram / sequence
  "entities": ["订单服务", "支付服务", "用户服务", "API网关"],
  "connections": [
    {"source": "订单服务", "target": "支付服务", "label": "gRPC"},
    {"source": "API网关", "target": "订单服务", "label": "HTTP"}
  ],
  "visual_embedding": [0.312, -0.845, ...],  # ⭐⭐ CLIP 视觉 Embedding（768d, 用于以图搜图）
  "text_embedding": [0.267, -0.712, ...],     # ⭐⭐ CLIP 文本 Embedding（768d, 用于文搜图）
  "linked_entity_ids": ["entity-uuid-1", "entity-uuid-2"],
  "source_doc": "PRD-v3.2.pdf",
  "created_at": "2026-07-15T10:30:00Z"
}

DiagramTemplate:
{
  "id": "DT-deploy-microservice",
  "name": "微服务部署拓扑图",
  "type": "deployment",               # architecture / flow / deployment / er
  "format": "mermaid",                 # mermaid / plantuml
  "template_code": "flowchart TB\n    subgraph {{name}}[...]\n    end",
  "parameters": ["components", "relations", "protocols"],
  "style_config": {"theme": "default", "direction": "TB"},
  "version": "1.0"
}
```

### 3.4 知识图谱生命周期管理

```
┌─────────────────────────────────────────────────────────────────────┐
│                     知识图谱生命周期                                  │
│                                                                      │
│  文档上传                                                             │
│     │                                                                │
│     ▼                                                                │
│  ┌──────────┐                                                        │
│  │ 多粒度分块 │  (Sentence / Paragraph / Section 三级)                 │
│  └────┬─────┘                                                        │
│       │                                                              │
│  ┌────▼─────┐    ┌──────────┐    ┌──────────┐                       │
│  │ 实体提取  │───→│ 实体融合  │───→│ 人工审核  │                       │
│  │ (AI)     │    │ (去重合并)│    │ (可选)   │                       │
│  └────┬─────┘    └──────────┘    └─────┬────┘                       │
│       │                               │                             │
│  ┌────▼─────┐    ┌──────────┐          │                            │
│  │ 关系提取  │───→│ 关系验证  │──────────┘                            │
│  │ (AI)     │    │ (冲突检测)│                                       │
│  └────┬─────┘    └──────────┘                                       │
│       │                                                              │
│  ┌────▼─────┐                                                        │
│  │ TextUnit │  构建中间层（Chunk ↔ Entity 桥梁）                      │
│  │ 构建     │  携带原文证据 + Embedding                               │
│  └────┬─────┘                                                        │
│       │                                                              │
│  ┌────▼──────┐                                                       │
│  │ Claims    │  提取声明性断言（对比/决策/规格/约束）                  │
│  │ 提取      │  存入 Neo4j + PGVector                                │
│  └────┬──────┘                                                       │
│       │                                                              │
│  ┌────▼─────────┐                                                    │
│  │ ⭐⭐ CLIP     │  多模态视觉 Embedding + ImageChunk 构建            │
│  │  多模态提取   │  视觉768d + 文本768d 双向量 → PGVector             │
│  └────┬─────────┘                                                    │
│       │                                                              │
│  ┌────▼─────┐                                                        │
│  │ 实体     │  多源融合 Embedding（名称+描述+TextUnit+Claims+视觉）   │
│  │ Embedding│  写入 Neo4j 实体属性                                    │
│  └────┬─────┘                                                        │
│       │                                                              │
│  ┌────▼──────┐                                                       │
│  │ Leiden    │  社区检测（多层级 Level 0 → N）                        │
│  │ 社区检测   │  生成社区层级树                                       │
│  └────┬──────┘                                                       │
│       │                                                              │
│  ┌────▼──────┐                                                       │
│  │ Community │  为每个社区生成摘要报告                                 │
│  │ Report    │  存入 PGVector（供 Global Search）                     │
│  └────┬──────┘                                                       │
│       │                                                              │
│  ┌────▼───────────────────────────────────────┐                      │
│  │              知识图谱存储 (版本化)            │                      │
│  │  版本v1  ←  版本v2  ←  版本v3  ←  ...      │                      │
│  └────────────────────────────────────────────┘                      │
│       │                                                              │
│  ┌────▼───────────────────────────────────────┐                      │
│  │              老化与淘汰策略                  │                      │
│  │  - 90天未引用 → 降权                        │                      │
│  │  - 180天未引用 → 归档                       │                      │
│  │  - 365天未引用 → 标记删除                    │                      │
│  │  - Claims 时效性过期 → 标记可疑              │                      │
│  └────────────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 3.4.1 实体融合（Entity Resolution）

```python
class EntityResolver:
    """
    同一实体来自不同源的合并策略
    策略：精确匹配 > 别名匹配 > 语义相似度 > 人工确认
    """
    
    RESOLUTION_STRATEGIES = [
        ("exact_name",          self.match_exact_name,          1.0),
        ("alias_match",         self.match_alias,               0.95),
        ("name_similarity",     self.match_semantic,            0.85),
        ("context_overlap",     self.match_context,             0.75),
        ("human_review",        self.request_human_review,      0.5),
    ]
    
    def resolve(self, new_entity: KGEntity, 
                existing: list[KGEntity]) -> tuple[KGEntity, str]:
        """
        返回: (最终实体, 操作类型: 'new'/'merge'/'skip')
        """
        for strategy_name, strategy_fn, threshold in self.RESOLUTION_STRATEGIES:
            match, score = strategy_fn(new_entity, existing)
            if match and score >= threshold:
                if score >= 0.95:
                    # 高度匹配 → 合并属性
                    merged = self.merge_entities(match, new_entity)
                    return merged, "merge"
                elif score >= 0.75:
                    # 中度匹配 → 标记为候选合并，等待人工确认
                    self.mark_as_candidate(match, new_entity, score)
                    return new_entity, "pending_review"
                else:
                    # 低度匹配 → 作为新实体
                    return new_entity, "new"
        return new_entity, "new"
```

#### 3.4.2 知识老化策略

```python
class KnowledgeAgingPolicy:
    """
    知识老化与淘汰 - 确保知识图谱质量
    """
    
    def apply_aging(self):
        """定期执行老化策略"""
        now = datetime.utcnow()
        
        # 1. 降权处理（90天未引用）
        stale_entities = self.get_unreferenced_entities(days=90)
        for entity in stale_entities:
            self.graph_store.update_entity(
                entity.id,
                {"confidence": entity.confidence * 0.8}
            )
        
        # 2. 归档处理（180天未引用）
        archive_entities = self.get_unreferenced_entities(days=180)
        for entity in archive_entities:
            self.graph_store.move_to_archive(entity.id)
        
        # 3. 软删除（365天未引用）
        delete_entities = self.get_unreferenced_entities(days=365)
        for entity in delete_entities:
            self.graph_store.soft_delete(entity.id)
        
        logger.info(
            f"知识老化完成: 降权{len(stale_entities)}个, "
            f"归档{len(archive_entities)}个, 删除{len(delete_entities)}个"
        )
```

#### 3.4.3 完整多模态 RAG 体系

完整多模态 RAG 比原有单向提取扩展为 **三条双向管道**：

```
                         ┌──────────────────────────────────────────┐
                         │           完整多模态 RAG                   │
                         │                                          │
  ┌────────────────┐    ┌──────────────────────────────────────────┐ │
  │                │    │  管道 A: 图片→文本（原有→增强）            │ │
  │  PRD 图片/图表  │───→│  视觉 LLM 提取 → 结构化知识 → 图谱写入    │ │
  │  架构图/流程图  │    │  + 新增: ImageChunk(视觉Token) 索引       │ │
  │                │    └─────────────────────┬────────────────────┘ │
  └────────────────┘                          │                     │
        │                                     ▼                     │
        │                            ┌──────────────────────────┐   │
        │                            │  管道 B: 文本→图片（新增）  │   │
        │                            │  方案描述 → Mermaid/PlantUML│   │
        │                            │  → 渲染为 SVG/PNG 嵌入输出  │   │
        │                            └──────────────────────────┘   │
        │                                                           │
        ▼                                                           │
  ┌─────────────────────────────────────────────────────────────┐   │
  │  管道 C: 以图搜图 / 图文混合检索（新增）                      │   │
  │  CLIP 双塔模型: image_embedding + text_embedding 同一空间    │   │
  │  → 用户上传图片找相似架构图                                  │   │
  │  → 文本描述找匹配的架构图                                    │   │
  │  → 图文混合检索融合排序                                      │   │
  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

##### 管道 A 增强版：图片 → 结构 + 向量双写

```python
class MultimodalKnowledgeExtractor:
    """
    完整多模态知识提取 - 从图片提取结构化知识 + 视觉 Embedding 双写
    使用 GPT-4o/Claude 的视觉能力 + CLIP 视觉 Embedding
    """
    
    def __init__(self):
        self.vision_llm = get_vision_llm()       # GPT-4o / Claude
        self.clip_model = CLIPModel.from_pretrained(
            "openai/clip-vit-large-patch14"       # 或 BAAI/bge-visualized
        )
        self.clip_processor = CLIPProcessor.from_pretrained(
            "openai/clip-vit-large-patch14"
        )
    
    def extract_from_image(self, image_path: str) -> ImageKnowledge:
        """
        从架构图/流程图提取结构化知识
        同时生成视觉 Embedding 用于以图搜图
        """
        # === 阶段1: LLM 视觉理解（提取结构化知识） ===
        result = self.vision_llm.complete(f"""
        分析这张技术架构图/流程图，提取：
        
        1. 组件列表：图中的所有系统/模块/服务
        2. 连接关系：组件之间的连线/箭头代表什么关系
        3. 数据流：数据的流向
        4. 协议标签：HTTP/gRPC/MQ等协议标注
        5. 外部系统：与外部系统的交互
        
        输出 JSON 格式：
        {{
            "components": [{{"name": "订单服务", "type": "service", "bounding_box": [x1,y1,x2,y2]}}],
            "connections": [{{"source": "订单服务", "target": "支付服务", "label": "gRPC", "type": "sync"}}],
            "external_systems": ["微信支付", "物流API"],
            "diagram_type": "architecture",  # architecture / flow / ui_wireframe
            "description": "整体采用微服务架构，...",
        }}
        """, image=image_path)
        
        knowledge = ImageKnowledge(**json.loads(result.text))
        
        # === 阶段2: CLIP 视觉 Embedding（用于以图搜图） ===
        image = Image.open(image_path)
        inputs = self.clip_processor(images=image, return_tensors="pt")
        with torch.no_grad():
            visual_embedding = self.clip_model.get_image_features(**inputs)
            visual_embedding = visual_embedding / visual_embedding.norm(
                dim=-1, keepdim=True
            )
        
        knowledge.visual_embedding = visual_embedding.squeeze().tolist()
        knowledge.image_path = image_path
        
        return knowledge
    
    def build_graph_from_image(self, image_knowledge: ImageKnowledge):
        """将图片提取的知识写入知识图谱 - 实体 + 关系 + 图片索引"""
        entities = []
        for comp in image_knowledge.components:
            entities.append(KGEntity(
                name=comp.name,
                type="Component",
                category="service",
                source="visual_extraction",
                confidence=0.8,
            ))
        
        relations = []
        for conn in image_knowledge.connections:
            relations.append(KGRelation(
                source=conn.source,
                target=conn.target,
                type="depends_on" if conn.type == "sync" else "references",
                metadata={"protocol": conn.label},
            ))
        
        self.graph_store.upsert_entities(entities)
        self.graph_store.upsert_relations(relations)
        
        # ★ 新增: 同时写入 ImageChunk（图片向量索引）
        image_chunk = ImageChunk(
            id=f"IMG-{str(uuid4())[:8]}",
            image_path=image_knowledge.image_path,
            description=image_knowledge.description,
            diagram_type=image_knowledge.diagram_type,
            entities=[e.name for e in image_knowledge.components],
            connections=image_knowledge.connections,
            visual_embedding=image_knowledge.visual_embedding,
            # 文本侧 Embedding（用描述做语义检索）
            text_embedding=self.embed_model.embed(
                f"[{image_knowledge.diagram_type}] {image_knowledge.description}"
                + "\n组件: " + ", ".join([c["name"] for c in image_knowledge.components])
            ),
            metadata={
                "source_doc": image_knowledge.source_doc,
                "extracted_at": datetime.utcnow().isoformat(),
                "component_count": len(image_knowledge.components),
            },
        )
        # 写入 PGVector（双向量: 视觉 + 文本）
        self.vector_store.upsert_image_chunk(image_chunk)
        
        return image_chunk
```

##### 管道 B：文本 → 架构图/图表生成

```python
class DiagramGenerator:
    """
    文本描述 → 架构图/流程图/部署图 自动生成
    输入: 架构规划结果中的组件关系、数据流
    输出: Mermaid/PlantUML → 渲染为 PNG/SVG → 嵌入最终方案文档
    """
    
    def generate_architecture_diagram(self, 
                                       components: list[Component],
                                       relations: list[KGRelation]) -> GeneratedDiagram:
        """从组件分解生成架构图"""
        
        # 策略1: Mermaid 语法生成（默认，高可编辑性）
        mermaid_code = self._components_to_mermaid(components, relations)
        
        # 策略2: PlantUML 语法生成（备选）
        plantuml_code = self._components_to_plantuml(components, relations)
        
        # 渲染为图片
        png_bytes = self._render_mermaid_to_png(mermaid_code)
        svg_content = self._render_mermaid_to_svg(mermaid_code)
        
        return GeneratedDiagram(
            diagram_type="architecture",
            mermaid_code=mermaid_code,
            plantuml_code=plantuml_code,
            png_base64=base64.b64encode(png_bytes).decode(),
            svg_content=svg_content,
        )
    
    def generate_flow_diagram(self, 
                               flows: list[DataFlow],
                               components: list[Component]) -> GeneratedDiagram:
        """从数据流分析生成流程图"""
        mermaid_code = "flowchart TD\n"
        for flow in flows:
            mermaid_code += (
                f"    {flow.source}[{flow.source_label}]"
                f"-->{|{flow.protocol}|}"
                f"{flow.target}[{flow.target_label}]\n"
            )
        
        png_bytes = self._render_mermaid_to_png(mermaid_code)
        return GeneratedDiagram(
            diagram_type="data_flow",
            mermaid_code=mermaid_code,
            png_base64=base64.b64encode(png_bytes).decode(),
        )
    
    def generate_deployment_diagram(self, 
                                     deploy: DeploymentPlan) -> GeneratedDiagram:
        """从部署方案生成部署拓扑图"""
        # Mermaid 部署拓扑
        mermaid_code = "flowchart TB\n"
        mermaid_code += "    subgraph LB[负载均衡]\n"
        for svc in deploy.services:
            mermaid_code += f"    {svc.id}[{svc.name}]\n"
        mermaid_code += "    end\n"
        # ... 更多生成逻辑
        
        return GeneratedDiagram(
            diagram_type="deployment",
            mermaid_code=mermaid_code,
            png_base64=...,
        )
    
    def _components_to_mermaid(self, components: list[Component],
                                relations: list[KGRelation]) -> str:
        """组件关系 → Mermaid 架构图"""
        code = "flowchart TB\n"
        # 按类型分组
        services = [c for c in components if c.type == "service"]
        modules = [c for c in components if c.type == "module"]
        
        if services:
            code += "    subgraph Services[微服务]\n"
            for s in services:
                code += f"        {s.name}[{s.name}]\n"
            code += "    end\n"
        if modules:
            code += "    subgraph Modules[内部模块]\n"
            for m in modules:
                code += f"        {m.name}[{m.name}]\n"
            code += "    end\n"
        
        for r in relations:
            code += f"    {r.source}-->{r.target}\n"
        
        return code
    
    def _render_mermaid_to_png(self, mermaid_code: str) -> bytes:
        """Mermaid → PNG (使用 mermaid-cli / Kroki API)"""
        try:
            # 方式1: 本地 mermaid-cli (mmdc)
            result = subprocess.run(
                ["mmdc", "-i", "-", "-o", "-", "-f", "png"],
                input=mermaid_code.encode(),
                capture_output=True, timeout=30,
            )
            return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # 方式2: Kroki 在线渲染 (自托管)
            response = requests.post(
                f"{settings.KROKI_URL}/mermaid/svg",
                json={"diagram": mermaid_code},
                timeout=15,
            )
            return response.content
```

##### 管道 C：以图搜图 + 图文混合检索

```python
class MultimodalSearchEngine:
    """
    多模态检索 - 支持以图搜图 + 图文混合查询
    
    架构:
    ┌──────────┐    ┌──────────────┐    ┌──────────┐
    │ 图片查询  │───→│  CLIP 编码   │───→│ PGVector  │
    │          │    │  visual emb  │    │ 余弦相似度│
    └──────────┘    └──────────────┘    └─────┬────┘
                                              │
    ┌──────────┐    ┌──────────────┐          │
    │ 文本查询  │───→│  CLIP 编码   │──────────┘
    │          │    │  text emb    │  (图文同一向量空间)
    └──────────┘    └──────────────┘
    """
    
    def __init__(self):
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
        self.vector_store = PGVectorStore()  # 存储 ImageChunk 双向量
    
    def search_by_image(self, image_path: str, top_k: int = 10) -> list[ScoredImageChunk]:
        """以图搜图 - 用图片找相似架构图"""
        # 1. 计算查询图片的视觉 Embedding
        image = Image.open(image_path)
        inputs = self.clip_processor(images=image, return_tensors="pt")
        with torch.no_grad():
            query_emb = self.clip_model.get_image_features(**inputs)
            query_emb = query_emb / query_emb.norm(dim=-1, keepdim=True)
        
        # 2. PGVector 视觉向量检索
        results = self.vector_store.search_image_by_visual(
            query_emb.squeeze().tolist(), top_k=top_k
        )
        return results
    
    def search_by_text(self, query: str, top_k: int = 10) -> list[ScoredImageChunk]:
        """文搜图 - 用文字描述找匹配架构图"""
        # 1. 计算查询文本的 CLIP Embedding
        inputs = self.clip_processor(text=[query], return_tensors="pt", 
                                      padding=True, truncation=True)
        with torch.no_grad():
            query_emb = self.clip_model.get_text_features(**inputs)
            query_emb = query_emb / query_emb.norm(dim=-1, keepdim=True)
        
        # 2. PGVector 文本向量检索（ImageChunk 存有 text_embedding）
        results = self.vector_store.search_image_by_text(
            query_emb.squeeze().tolist(), top_k=top_k
        )
        return results
    
    def search_hybrid(self, query: str, image_path: str = None,
                      top_k: int = 10) -> list[ScoredImageChunk]:
        """图文混合检索 - 融合文本 + 图片查询结果"""
        all_results = []
        
        # 文本检索 ImageChunk
        text_results = self.search_by_text(query, top_k=top_k)
        for r in text_results:
            r.score *= 0.6  # 文本权重 0.6
            all_results.append(r)
        
        # 如果有图片，同时以图搜图
        if image_path:
            image_results = self.search_by_image(image_path, top_k=top_k)
            for r in image_results:
                r.score *= 0.4  # 图片权重 0.4
                all_results.append(r)
        
        # RRF 融合 + 去重
        return self._rrf_fusion_multimodal(all_results)[:top_k]
    
    def _rrf_fusion_multimodal(self, results: list) -> list:
        """多模态 RRF 融合"""
        seen = set()
        fused = []
        for rank, r in enumerate(sorted(results, key=lambda x: x.score, reverse=True)):
            if r.id not in seen:
                seen.add(r.id)
                r.rrf_score = sum(
                    1 / (60 + j) for j, rr in enumerate(results) if rr.id == r.id
                )
                fused.append(r)
        return sorted(fused, key=lambda x: x.rrf_score, reverse=True)
```

##### ImageChunk 模型定义

```python
class ImageChunk(BaseModel):
    """图片单元 - 多模态 RAG 的核心数据模型"""
    id: str                                           # IMG-a1b2c3d4
    image_path: str                                   # MinIO 存储路径
    thumbnail_path: Optional[str]                     # 缩略图路径
    description: str                                  # LLM 生成的文字描述
    diagram_type: Literal["architecture", "flow", 
                          "deployment", "ui_wireframe",
                          "er_diagram", "sequence"]    # 图表类型
    entities: list[str]                               # 图中包含的组件/实体名
    connections: list[dict]                           # 连接关系 [{source, target, label}]
    
    # ★ 双向量：同一 CLIP 空间的视觉 + 文本向量
    visual_embedding: list[float]                     # CLIP image_features (768d)
    text_embedding: list[float]                       # CLIP text_features (768d)
    
    # 元数据
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # 关联的实体 IDs（链接到 Neo4j 图）
    linked_entity_ids: list[str] = []
    
    class Config:
        arbitrary_types_allowed = True
```

#### 3.4.4 知识图谱版本控制

```python
class KnowledgeGraphVersioning:
    """
    知识图谱版本控制 - 支持回滚和差异查看
    每次变更写入一个版本快照
    """
    
    def create_snapshot(self, reason: str = ""):
        """创建当前知识图谱的快照"""
        version_id = str(uuid4())
        snapshot = {
            "version_id": version_id,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
            "entities": self.graph_store.export_all_entities(),
            "relations": self.graph_store.export_all_relations(),
        }
        self.object_store.put(
            f"kg_snapshots/{version_id}.json",
            json.dumps(snapshot, ensure_ascii=False)
        )
        return version_id
    
    def rollback(self, version_id: str):
        """回滚到指定版本"""
        snapshot = self.object_store.get(f"kg_snapshots/{version_id}.json")
        data = json.loads(snapshot)
        
        # 清空当前图并重建
        self.graph_store.clear_all()
        self.graph_store.import_entities(data["entities"])
        self.graph_store.import_relations(data["relations"])
        
        logger.info(f"知识图谱已回滚到版本 {version_id}: {data.get('reason', '')}")
```

### 3.5 多路检索 — Local Search 与 Global Search

#### 3.5.1 检索模式总览

```
检索路由决策树：
                        用户查询
                           │
                    ┌──────▼──────┐
                    │ Intent Router│
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┼────────────┐
              ▼            ▼            ▼            ▼
        "find_entity"  "summarize"   "mixed"    "visual"
        （查找实体）     （全局概括）   （混合）   （⭐多模态）
              │            │            │            │
              ▼            ▼            ▼            ▼
        Local Search  Global Search  Hybrid Search  Multimodal Search
              │            │            │            │
    ┌─────────┴────┐      │      ┌─────┴─────┐      │
    │ 子图遍历     │      │      │ Local结果  │  ┌───┴──────────────┐
    │ TextUnit证据 │      │      │ + Global   │  │ CLIP 双塔编码     │
    │ Claims上下文 │      │      │ 上下文补充 │  │ 视觉+文本同一空间  │
    └──────────────┘      │      └───────────┘  │ PGVector 双向量检索 │
                          │                     │ 以图搜图 / 文搜图   │
                   ┌──────┴──────────┐          │ 图文混合 RRF 融合  │
                   │ 社区报告检索     │          └────────────────────┘
                   │ (向量相似度匹配) │
                   │ 多层级聚合       │
                   │ (Level 0→N)     │
                   └─────────────────┘

检索模式对比：
┌───────────────┬──────────────────────┬──────────────────────┬──────────────────────────┐
│ 维度          │ Local Search         │ Global Search        │ ⭐ Multimodal Search      │
├───────────────┼──────────────────────┼──────────────────────┼──────────────────────────┤
│ 目标          │ 回答关于特定实体/    │ 回答关于整体主题的   │ 以图搜图 / 文搜图        │
│               │ 组件的具体问题       │ 概括性问题            │ 图文混合查询             │
├───────────────┼──────────────────────┼──────────────────────┼──────────────────────────┤
│ 数据源        │ 实体+关系子图        │ 社区摘要报告          │ ImageChunk（双向量）     │
│               │ TextUnit 原文证据    │ (CommunityReport)     │ 视觉768d+文本768d        │
│               │ Claims 声明上下文    │ 高层级社区            │ MinIO 原图+缩略图         │
├───────────────┼──────────────────────┼──────────────────────┼──────────────────────────┤
│ 检索方式       │ 图遍历+向量匹配     │ 向量相似度匹配        │ CLIP 双塔编码             │
│               │ +String搜索          │ + 层级遍历            │ 余弦相似度 + RRF 融合    │
├───────────────┼──────────────────────┼──────────────────────┼──────────────────────────┤
│ 典型问题      │ "用户服务用了什么    │ "这个项目的整体      │ "找一张和这张类似的      │
│               │  技术栈？"           │  架构是怎样的？"      │  架构图"                 │
│               │ "认证流程如何设计？" │ "有哪些核心设计决策？" │ "画一个订单系统的部署图" │
├───────────────┼──────────────────────┼──────────────────────┼──────────────────────────┤
│ 输出格式       │ 实体卡片+原文引用    │ 结构化摘要+来源报告   │ ImageChunk 卡片          │
│               │ +关系图+证据文本     │ +关键发现列表         │ +相似架构图缩略图        │
│               │                      │                      │ +原图+关联实体链接       │
└───────────────┴──────────────────────┴──────────────────────┴──────────────────────────┘
```

#### 3.5.2 Local Search 实现

```python
class LocalSearchEngine:
    """
    Local Search — 针对特定实体/组件的精细查询
    
    检索流程：
    1. 实体匹配（精确+语义）→ 定位目标实体
    2. 子图遍历（1-2跳邻居）→ 收集相关实体和关系
    3. TextUnit 召回 → 找到实体的原文上下文
    4. Claims 召回 → 找到相关的声明性断言
    5. 上下文组装 → 结构化输出
    """
    
    def search(self, query: str, top_k: int = 10) -> LocalSearchResult:
        """
        Local Search 主入口
        """
        # Step 1: 实体匹配 — 找到查询中提到的实体
        matched_entities = self._match_entities(query)
        
        # Step 2: 子图扩展 — 从匹配实体出发探索邻居
        subgraph = self._expand_subgraph(
            matched_entities,
            max_hops=2,           # 最多2跳
            max_nodes=50,         # 子图上限
        )
        
        # Step 3: TextUnit 召回 — 找到实体的原文证据
        text_units = self._retrieve_text_units(subgraph.entities)
        
        # Step 4: Claims 召回 — 相关的声明性断言
        claims = self._retrieve_claims(subgraph.entities)
        
        # Step 5: 上下文组装
        return self._assemble_local_context(
            query=query,
            matched_entities=matched_entities,
            subgraph=subgraph,
            text_units=text_units,
            claims=claims,
        )
    
    def _match_entities(self, query: str) -> list[ScoredEntity]:
        """实体匹配 — 精确 + 语义两阶段"""
        # 阶段1: 精确/模糊文本匹配（Neo4j full-text）
        exact_matches = self.graph_store.text_search_entities(
            query, top_k=20
        )
        
        # 阶段2: 语义匹配（Embedding 相似度）
        query_embedding = self.embed_model.embed(query)
        semantic_matches = self.graph_store.vector_search_entities(
            query_embedding, top_k=20
        )
        
        # RRF 融合 + 去重
        fused = self._rrf_fusion(exact_matches, semantic_matches)
        return fused[:10]
    
    def _expand_subgraph(self, seed_entities: list[ScoredEntity],
                         max_hops: int, max_nodes: int) -> SubGraph:
        """子图遍历扩展"""
        # Neo4j Cypher: 从种子实体出发，沿关系遍历 max_hops 步
        query = """
        MATCH (seed:Entity)-[r*1..{max_hops}]-(neighbor:Entity)
        WHERE seed.id IN {seed_ids}
        RETURN seed, r, neighbor
        LIMIT {max_nodes}
        """
        
        nodes, edges = self.graph_store.execute_subgraph_query(
            seed_ids=[e.id for e in seed_entities],
            max_hops=max_hops,
            max_nodes=max_nodes,
        )
        
        return SubGraph(
            entities=nodes,
            relations=edges,
            seed_ids=[e.id for e in seed_entities],
        )
    
    def _retrieve_text_units(self, entities: list[Entity]) -> list[TextUnit]:
        """召回与实体关联的 TextUnit"""
        # 通过 extracted_from 关系找到 TextUnit
        entity_ids = [e.id for e in entities]
        return self.graph_store.get_text_units_for_entities(
            entity_ids, top_k=15
        )
    
    def _retrieve_claims(self, entities: list[Entity]) -> list[Claim]:
        """召回实体的 Claims"""
        entity_ids = [e.id for e in entities]
        return self.graph_store.get_claims_for_entities(
            entity_ids, top_k=10
        )
    
    def _assemble_local_context(self, query, matched_entities,
                                subgraph, text_units,
                                claims) -> LocalSearchResult:
        """
        组装 Local Search 结果
        
        输出格式：
        - matched_entities: 匹配到的实体列表（含相似度）
        - subgraph_summary: 子图中的关键关系
        - text_unit_evidence: 原文证据引用
        - claims_evidence: 声明性断言
        - related_entities: 相关但未直接匹配的实体
        """
        return LocalSearchResult(
            query=query,
            matched_entities=[
                {
                    "name": e.name,
                    "type": e.type,
                    "score": e.score,
                    "description": e.description,
                }
                for e in matched_entities[:5]
            ],
            relations=[
                {
                    "source": r.source_name,
                    "target": r.target_name,
                    "type": r.type,
                    "reason": r.reason,
                }
                for r in subgraph.relations[:20]
            ],
            text_unit_evidence=[
                {
                    "text": tu.text[:500],
                    "section": tu.metadata.get("section_path", ""),
                    "entities": tu.entity_names,
                }
                for tu in text_units[:8]
            ],
            claims_evidence=[
                {
                    "type": c.claim_type,
                    "claim": c.claim,
                    "confidence": c.confidence,
                }
                for c in claims[:5]
            ],
        )
```

#### 3.5.3 Global Search 实现

```python
class GlobalSearchEngine:
    """
    Global Search — 针对宏观主题的概括性查询
    
    检索流程：
    1. 查询向量化 → 匹配 CommunityReport
    2. 确定合适的社区层级（Level selection）
    3. 收集匹配报告的摘要+关键发现
    4. LLM 聚合生成最终答案
    
    与 Local Search 的本质区别：
    - Local: 查实体→看邻居→读原文（自底向上）
    - Global: 匹配报告→选层级→汇总（自顶向下）
    """
    
    def search(self, query: str, top_k: int = 10) -> GlobalSearchResult:
        """Global Search 主入口"""
        
        # Step 1: 社区报告匹配（向量相似度）
        query_embedding = self.embed_model.embed(query)
        matched_reports = self.vector_store.search_community_reports(
            query_embedding, top_k=top_k * 2
        )
        
        # Step 2: 层级选择 — 根据查询粒度选合适的 Level
        target_level = self._select_level(query, matched_reports)
        filtered_reports = [
            r for r in matched_reports
            if abs(r.level - target_level) <= 1  # 允许±1级
        ]
        
        # Step 3: 收集跨社区的全局洞察
        cross_community_insights = self._collect_cross_community(
            filtered_reports
        )
        
        # Step 4: LLM 聚合生成答案
        answer = self._generate_global_answer(
            query=query,
            reports=filtered_reports[:top_k],
            insights=cross_community_insights,
        )
        
        return GlobalSearchResult(
            query=query,
            answer=answer,
            source_reports=[
                {"title": r.title, "level": r.level, "score": r.score}
                for r in filtered_reports[:top_k]
            ],
            key_findings=cross_community_insights,
        )
    
    def _select_level(self, query: str,
                      reports: list[ScoredReport]) -> int:
        """
        智能层级选择：
        - "整体架构"、"项目概述" → 高层级 (Level 2-3，粗粒度)
        - "认证模块"、"数据库设计" → 中介层级 (Level 1)
        - "某个接口"、"具体配置" → 低层级 (Level 0，细粒度)
        """
        # 按单词数/特异性判断粒度
        broad_keywords = ["整体", "全局", "概览", "架构", "overview",
                         "architecture", "总结", "summary", "全景"]
        specific_keywords = ["接口", "配置", "参数", "字段", "api",
                            "endpoint", "具体", "某个", "这个"]
        
        query_lower = query.lower()
        if any(kw in query_lower for kw in broad_keywords):
            return min(r.level for r in reports) + 2  # 偏高层级
        elif any(kw in query_lower for kw in specific_keywords):
            return max(r.level for r in reports)       # 偏细粒度
        else:
            # 默认选中间层级
            levels = [r.level for r in reports]
            return levels[len(levels) // 2] if levels else 0
    
    def _collect_cross_community(self,
                                 reports: list[ScoredReport]) -> list[dict]:
        """收集跨社区的关键发现"""
        all_findings = []
        for report in reports:
            for finding in report.findings:
                # 检查是否跨越多个社区（跨社区发现更有价值）
                if self._is_cross_community_finding(finding):
                    all_findings.append({
                        "finding": finding["content"],
                        "type": finding.get("type", ""),
                        "source_community": report.title,
                        "is_cross_community": True,
                    })
        
        # 去重相似发现
        return self._deduplicate_findings(all_findings)
    
    def _generate_global_answer(self, query: str,
                                reports: list[ScoredReport],
                                insights: list[dict]) -> str:
        """用 LLM 从匹配的社区报告生成综合答案"""
        
        GLOBAL_ANSWER_PROMPT = """
        你是一个技术方案分析专家。根据以下社区摘要报告，回答用户的问题。
        
        ## 用户问题
        {query}
        
        ## 相关社区摘要（共 {report_count} 个）
        {reports}
        
        ## 跨社区洞察
        {insights}
        
        请生成一个全面的回答：
        1. 直接回答用户的问题
        2. 引用具体的社区报告作为依据
        3. 如果涉及多个社区，说明它们之间的关系
        4. 如果有跨社区的关键发现，重点突出
        
        回答格式：结构化的 Markdown
        """
        
        reports_text = "\n\n---\n\n".join([
            f"### [{r.level}] {r.title}\n{r.summary}\n"
            f"关键实体：{', '.join([e['name'] for e in r.key_entities])}\n"
            f"关键发现：{'; '.join([f['content'] for f in r.findings[:3]])}"
            for r in reports[:8]
        ])
        
        insights_text = "\n".join([
            f"- [{i['source_community']}] {i['finding']}"
            for i in insights[:10]
        ])
        
        return self.llm.complete(
            GLOBAL_ANSWER_PROMPT.format(
                query=query,
                report_count=len(reports),
                reports=reports_text,
                insights=insights_text,
            )
        ).text
```

#### 3.5.4 更新 RetrievalPipeline（整合两种模式）

```python
class RetrievalPipeline:
    """完整检索流水线 — 整合 Local + Global + ⭐ Multimodal Search"""
    
    def __init__(self):
        self.intent_router = IntentRouter()
        self.query_rewriter = QueryRewriter()
        self.query_enricher = QueryEnricher()
        self.local_search = LocalSearchEngine()
        self.global_search = GlobalSearchEngine()
        self.multimodal_search = MultimodalSearchEngine()  # ⭐ 新增: 多模态检索
        self.diagram_generator = DiagramGenerator()         # ⭐ 新增: 图表生成
        self.reranker = CrossEncoderReRanker()
        self.compressor = ContextCompressor()
    
    def retrieve(self, query: str = None, intent: str = "auto",
                 top_k: int = 10, image_path: str = None) -> RetrievalContext:
        """
        检索主入口（支持文本 + ⭐图片 双模式）
        
        Args:
            query: 文本查询（可选，以图搜图时可为空）
            intent: 意图模式 auto / local / global / hybrid / visual
            top_k: 返回结果数
            image_path: ⭐ 图片查询路径（以图搜图时传入）
        """
        # Step 0: ⭐ 检测是否包含图片查询
        has_image_query = image_path is not None
        
        # Step 1: Intent Router → 确定搜索模式
        if has_image_query and query:
            search_mode = "visual"  # 图文混合
        elif has_image_query:
            search_mode = "visual"  # 纯以图搜图
        else:
            search_mode = self.intent_router.route(query, intent)
        # 可能的输出: "local" | "global" | "hybrid" | "visual"
        
        # Step 2: Query Rewriter → 改写子查询
        rewritten_queries = self.query_rewriter.rewrite(query) if query else []
        
        # Step 3: Query Enricher → 实体链接扩展
        enriched_context = self.query_enricher.enrich(query) if query else {}
        
        # Step 4: 按模式执行检索
        if search_mode == "local":
            results = self._execute_local_search(
                query, rewritten_queries, enriched_context, top_k
            )
        elif search_mode == "global":
            results = self._execute_global_search(
                query, rewritten_queries, enriched_context, top_k
            )
        elif search_mode == "visual":
            results = self._execute_multimodal_search(
                query, image_path, top_k
            )
        else:  # hybrid
            results = self._execute_hybrid_search(
                query, rewritten_queries, enriched_context, top_k
            )
        
        # Step 5: Re-rank
        results = self.reranker.rerank(query or "", results)
        
        # Step 6: Context Compression
        results = self.compressor.compress(results, max_tokens=4000)
        
        return RetrievalContext(
            query=query or "(image_query)",
            search_mode=search_mode,
            docs=results,
            rewritten_queries=rewritten_queries,
            image_path=image_path,        # ⭐ 携带图片路径
        )
    
    def _execute_multimodal_search(self, query: str, image_path: str,
                                    top_k: int) -> list[ScoredDoc]:
        """
        ⭐ 多模态检索
        三种子模式：
        1. 纯以图搜图: image_path 有值, query=None
        2. 纯文搜图:   query 有值, image_path=None
        3. 图文混合:   query + image_path 都有值
        """
        all_candidates = []
        
        if image_path and query:
            # 模式3: 图文混合
            results = self.multimodal_search.search_hybrid(
                query, image_path, top_k=top_k
            )
            all_candidates.extend(self._imagechunk_to_scored_docs(results))
            
        elif image_path:
            # 模式1: 纯以图搜图
            results = self.multimodal_search.search_by_image(
                image_path, top_k=top_k
            )
            all_candidates.extend(self._imagechunk_to_scored_docs(results))
            
        elif query:
            # 模式2: 纯文搜图
            results = self.multimodal_search.search_by_text(
                query, top_k=top_k
            )
            all_candidates.extend(self._imagechunk_to_scored_docs(results))
            
            # 补充: 同时检索关联的文本实体（为文搜图补充上下文）
            text_results = self._execute_local_search(
                query, [query], {}, top_k // 2
            )
            all_candidates.extend(text_results)
        
        return all_candidates[:top_k]
    
    def _execute_local_search(self, query, rewritten_queries,
                              enriched, top_k) -> list[ScoredDoc]:
        """Local Search: 图检索 + 向量检索 + BM25 三路融合"""
        all_candidates = []
        
        for rq in rewritten_queries:
            # 路1: 图检索（子图遍历）
            graph_results = self.local_search.search(rq, top_k=top_k)
            all_candidates.extend(self._to_scored_docs(graph_results))
            
            # 路2: 语义检索（向量相似度 — 匹配 TextUnit）
            tu_results = self.vector_store.search_text_units(rq, top_k=top_k)
            all_candidates.extend(tu_results)
            
            # 路3: 全文检索（BM25）
            bm25_results = self.bm25_search.search(rq, top_k=top_k)
            all_candidates.extend(bm25_results)
        
        # RRF Fusion
        fused = self._rrf_fusion(all_candidates)
        return fused[:top_k]
    
    def _execute_global_search(self, query, rewritten_queries,
                               enriched, top_k) -> list[ScoredDoc]:
        """Global Search: 以社区报告匹配为主"""
        all_candidates = []
        
        for rq in rewritten_queries:
            # 社区报告向量匹配
            report_results = self.global_search.search(rq, top_k=top_k)
            all_candidates.extend(self._report_to_scored_docs(report_results))
        
        # 补充高层社区的结构信息
        high_level_reports = self.vector_store.search_community_reports(
            level_min=2, top_k=5  # Level 2+ 的高层摘要
        )
        all_candidates.extend(high_level_reports)
        
        # 去重 + 按层级排序（高层级优先）
        return self._deduplicate_by_level(all_candidates)[:top_k]
    
    def _execute_hybrid_search(self, query, rewritten_queries,
                               enriched, top_k) -> list[ScoredDoc]:
        """Hybrid Search: Local + Global 混合"""
        # 同时执行两种检索
        local_results = self._execute_local_search(
            query, rewritten_queries, enriched, top_k // 2
        )
        global_results = self._execute_global_search(
            query, rewritten_queries, enriched, top_k // 2
        )
        
        # 交替排列（Local结果为王，Global补充上下文）
        interleaved = []
        for i in range(max(len(local_results), len(global_results))):
            if i < len(local_results):
                interleaved.append(local_results[i])
            if i < len(global_results):
                interleaved.append(global_results[i])
        
        return interleaved[:top_k]
```

---

## 3.6 文件格式扩展：CSV / 表格数据支持

### 3.6.1 概述

CSV 与 Markdown/PDF 有本质区别——它是**结构化表格数据**而非叙事性文档。直接套用实体-关系-社区检测的 GraphRAG 流水线效果不佳。因此需要为 CSV 单独设计一套**行级/列级双通路索引策略**：

```
CSV 文件
   │
   ├── 管道 A（行级索引 — 每行=一个Chunk）──────────────┐
   │  每行 → 拼接为自然语言句子 → Paragraph 级 TextUnit   │
   │  → 实体提取（行中的关键字段值作为实体）               │
   │  → 行间关系（外键/关联列 → 关系提取）                │
   │  → 写入 Neo4j + PGVector                           │
   │                                                    │
   └── 管道 B（列级索引 — 每列=一个语义维度）──────────────┐
      列名+列描述 → 列级 Embedding                       │
      → 列值分布统计 → 枚举值实体化                       │
      → 列间相关性分析 → 协方差/互信息 → 关系图谱         │
      → 写入 PGVector（列级检索用）                      │
```

### 3.6.2 数据模型扩展

```python
# === CSV 相关数据模型 ===

class CSVTable(BaseModel):
    """CSV 表元信息"""
    id: str
    filename: str
    row_count: int
    column_count: int
    columns: list[CSVColumn]
    primary_key: Optional[str]           # 主键列名（自动检测或用户指定）
    foreign_keys: list[CSVForeignKey]    # 外键关系（跨文件关联用）
    row_chunks: list[CSVRowChunk]        # 行级 Chunk 列表
    created_at: str

class CSVColumn(BaseModel):
    """CSV 列定义"""
    name: str
    dtype: Literal["string", "integer", "float", "boolean", "date", "enum"]
    description: str                     # LLM 生成的列描述
    enum_values: list[str] = []          # 枚举值列表（dtype="enum" 时）
    null_ratio: float                    # 空值比例
    distinct_ratio: float                # 唯一值比例
    embedding: list[float]               # 列语义 Embedding（用于列级检索）
    
    # 统计摘要（LLM 生成）
    summary: Optional[str] = None        # "取值范围 1-100，中位数 45"

class CSVRowChunk(BaseModel):
    """行级 Chunk — 将一行数据转为自然语言"""
    id: str
    row_index: int                       # 原始行号
    text: str                            # 拼接后的自然语言句子
    entities: list[str]                  # 该行提取的实体 ID 列表
    embedding: list[float]               # 行级语义 Embedding

class CSVForeignKey(BaseModel):
    """CSV 跨表外键关系"""
    source_column: str                   # 当前表的列名
    target_table: str                    # 目标表名
    target_column: str                   # 目标表列名
    confidence: float                    # 自动检测置信度
```

### 3.6.3 加载器实现

```python
class CSVLoader:
    """
    CSV 文件加载 + 双通路索引
    支持常见的 CSV 方言（逗号/制表符分隔、引号转义、BOM 头等）
    """
    
    def __init__(self):
        self.llm = get_llm()
        self.embed_model = get_embedding()
    
    def load(self, file_path: str, 
             table_name: str = None,
             encoding: str = "utf-8",
             delimiter: str = ",",
             has_header: bool = True) -> CSVTable:
        """
        加载 CSV 并构建双通路索引
        
        Args:
            file_path: CSV 文件路径
            table_name: 表名（可选，默认用文件名）
            encoding: 文件编码
            delimiter: 分隔符（支持逗号/制表符/分号等）
            has_header: 是否有表头行
        """
        # === Phase 1: 解析 ===
        df = self._parse_csv(file_path, encoding, delimiter, has_header)
        
        # === Phase 2: 列分析（LLM 辅助） ===
        columns = self._analyze_columns(df, table_name or file_path)
        
        # === Phase 3: 行级自然语言化 ===
        row_chunks = self._rows_to_text_units(df, columns)
        
        # === Phase 4: 外键检测（跨文件时） ===
        foreign_keys = self._detect_foreign_keys(columns, table_name)
        
        # === Phase 5: 实体提取（从行内容中） ===
        entities = self._extract_entities_from_rows(df, columns, row_chunks)
        
        # === Phase 6: 写入存储 ===
        self._store(table_name, columns, row_chunks, entities, foreign_keys)
        
        return CSVTable(
            id=f"CSV-{str(uuid4())[:8]}",
            filename=os.path.basename(file_path),
            row_count=len(df),
            column_count=len(columns),
            columns=columns,
            primary_key=self._detect_primary_key(df, columns),
            foreign_keys=foreign_keys,
            row_chunks=row_chunks,
        )
    
    def _parse_csv(self, file_path: str, encoding: str,
                   delimiter: str, has_header: bool) -> pd.DataFrame:
        """解析 CSV 文件 — 自动处理编码和方言"""
        # 自动检测分隔符（如果未指定）
        if not delimiter:
            delimiter = self._detect_delimiter(file_path)
        
        try:
            df = pd.read_csv(
                file_path,
                encoding=encoding,
                sep=delimiter,
                header=0 if has_header else None,
                on_bad_lines="warn",       # 跳过格式错误的行
                dtype=str,                 # 先全部读为字符串
                keep_default_na=False,     # 保留空字符串而非 NaN
            )
        except UnicodeDecodeError:
            # 回退编码检测
            detected = chardet.detect(open(file_path, "rb").read(10000))
            df = pd.read_csv(
                file_path,
                encoding=detected.get("encoding", "utf-8"),
                sep=delimiter,
            )
        
        # 自动推断列类型
        df = df.infer_objects()
        return df
    
    def _detect_delimiter(self, file_path: str) -> str:
        """自动检测 CSV 分隔符"""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(4096)
        
        # 统计各种分隔符的出现频率
        candidates = {",": 0, "\\t": 0, ";": 0, "|": 0}
        for sep in candidates:
            candidates[sep] = len(sample.split(sep))
        
        # 选出现次数最多的（且>1列）
        best_sep = max(candidates, key=candidates.get)
        return best_sep if candidates[best_sep] > 1 else ","
    
    def _analyze_columns(self, df: pd.DataFrame, 
                         table_name: str) -> list[CSVColumn]:
        """LLM 辅助列分析 — 推断语义类型和描述"""
        
        # 先做统计预处理
        columns = []
        col_summaries = []
        
        for col in df.columns:
            non_null = df[col].dropna()
            null_ratio = 1 - len(non_null) / len(df)
            distinct = non_null.nunique()
            distinct_ratio = distinct / max(len(non_null), 1)
            
            # 判断基础类型
            dtype = self._infer_dtype(non_null, distinct_ratio)
            
            # 收集枚举值（如果是 enum 类型且值不多）
            enum_values = []
            if dtype == "enum" and distinct <= 50:
                enum_values = sorted(non_null.unique().tolist())
            
            col_summaries.append({
                "name": col,
                "dtype": dtype,
                "distinct_count": distinct,
                "null_ratio": round(null_ratio, 3),
                "sample_values": non_null.head(5).tolist(),
                "enum_values": enum_values[:20],  # 最多取20个示例
            })
        
        # 用 LLM 生成列描述
        result = self.llm.complete(f"""
        分析以下 CSV 表的列信息，为每列生成语义描述。
        
        表名：{table_name}
        总行数：{len(df)}
        
        列信息：
        {json.dumps(col_summaries, ensure_ascii=False, indent=2)}
        
        请为每列补充：
        1. description: 该列的业务含义（一句话）
        2. summary: 数据分布摘要（如果是数值列，描述范围/均值；如果是文本列，描述典型值）
        3. dtype 修正（如果 LLM 从列名能推断出更准确的类型）
        
        输出 JSON 列表：
        [{{"name": "user_id", "description": "用户唯一标识", "dtype": "string", "summary": "UUID格式，无重复"}}]
        """, response_format={"type": "json_object"})
        
        llm_columns = json.loads(result.text)
        
        # 合并统计信息和 LLM 描述
        for lc in llm_columns:
            stat = next(c for c in col_summaries if c["name"] == lc["name"])
            columns.append(CSVColumn(
                name=lc["name"],
                dtype=lc.get("dtype", stat["dtype"]),
                description=lc.get("description", ""),
                enum_values=stat.get("enum_values", []),
                null_ratio=stat["null_ratio"],
                distinct_ratio=stat.get("distinct_count", 0) / max(len(df), 1),
                summary=lc.get("summary"),
                embedding=self.embed_model.embed(
                    f"{lc['name']}: {lc.get('description', '')}"
                ).tolist(),
            ))
        
        return columns
    
    def _rows_to_text_units(self, df: pd.DataFrame,
                             columns: list[CSVColumn]) -> list[CSVRowChunk]:
        """每行拼接为自然语言句子 → TextUnit"""
        row_chunks = []
        
        for idx, row in df.iterrows():
            # 拼接该行所有列名为自然语言
            parts = []
            for col in columns:
                val = row.get(col.name, "")
                if val and str(val).strip():
                    parts.append(f"{col.description or col.name} 为 {val}")
            
            text = "；".join(parts)
            if not text.strip():
                continue
            
            chunk = CSVRowChunk(
                id=f"ROW-{str(uuid4())[:8]}",
                row_index=idx,
                text=text,
                entities=[],  # 后续由 entity_extractor 填充
                embedding=self.embed_model.embed(text).tolist(),
            )
            row_chunks.append(chunk)
        
        return row_chunks
    
    def _detect_foreign_keys(self, columns: list[CSVColumn],
                              table_name: str) -> list[CSVForeignKey]:
        """检测外键 — 列名包含 _id / Id 后缀的列"""
        foreign_keys = []
        for col in columns:
            # 启发式：列名以 _id / Id / ID / _key 结尾
            if re.search(r'[_](?:id|Id|ID|key|Key)$', col.name):
                # 推测目标表名：去掉后缀 + s
                target = re.sub(r'[_](?:id|Id|ID|key|Key)$', '', col.name) + "s"
                foreign_keys.append(CSVForeignKey(
                    source_column=col.name,
                    target_table=target,
                    target_column="id",
                    confidence=0.7,
                ))
        return foreign_keys
    
    def _detect_primary_key(self, df: pd.DataFrame,
                             columns: list[CSVColumn]) -> Optional[str]:
        """检测主键 — 唯一且非空比例最高的列"""
        best_col = None
        best_score = 0
        
        for col in columns:
            if col.null_ratio == 0 and col.distinct_ratio > 0.9:
                score = col.distinct_ratio
                if score > best_score:
                    best_score = score
                    best_col = col.name
        
        return best_col
    
    def _extract_entities_from_rows(self, df: pd.DataFrame,
                                     columns: list[CSVColumn],
                                     row_chunks: list[CSVRowChunk]) -> list[KGEntity]:
        """从行内容中提取实体 — 以关键列值为实体"""
        entities = []
        
        for col in columns:
            # 主键列/高区分度列 → 每行值作为一个实体
            if col.distinct_ratio > 0.8:
                values = df[col.name].dropna().unique()
                for val in values[:100]:  # 最多取100个
                    entities.append(KGEntity(
                        name=str(val),
                        type="DataRecord",
                        category=col.description or col.name,
                        description=f"{col.name} 中的值: {val}",
                        confidence=0.8,
                    ))
            # 低区分度列（枚举类）→ 枚举值作为实体
            elif col.dtype == "enum":
                for val in col.enum_values:
                    entities.append(KGEntity(
                        name=str(val),
                        type="EnumValue",
                        category=col.description or col.name,
                        description=f"{col.name} 的枚举值: {val}",
                        confidence=0.9,
                    ))
        
        return self.deduplicate_entities(entities)
    
    def _store(self, table_name: str, columns: list[CSVColumn],
               row_chunks: list[CSVRowChunk],
               entities: list[KGEntity],
               foreign_keys: list[CSVForeignKey]):
        """写入存储 — Neo4j + PGVector"""
        
        # 1. 写入 Neo4j（实体 + 行间关系）
        self.graph_store.upsert_entities(entities)
        
        # 2. 写入 PGVector（行级向量）
        for chunk in row_chunks:
            self.vector_store.upsert(
                id=chunk.id,
                text=chunk.text,
                embedding=chunk.embedding,
                metadata={
                    "type": "csv_row",
                    "table": table_name,
                    "row_index": chunk.row_index,
                },
            )
        
        # 3. 写入 PGVector（列级向量 — 用于列级检索）
        for col in columns:
            self.vector_store.upsert(
                id=f"COL-{table_name}-{col.name}",
                text=f"{col.name}: {col.description}",
                embedding=col.embedding,
                metadata={
                    "type": "csv_column",
                    "table": table_name,
                    "column": col.name,
                    "dtype": col.dtype,
                },
            )
    
    def deduplicate_entities(self, entities: list[KGEntity]) -> list[KGEntity]:
        """去重实体"""
        seen = set()
        unique = []
        for e in entities:
            key = (e.name, e.type)
            if key not in seen:
                seen.add(key)
                unique.append(e)
        return unique
```

### 3.6.4 CSV 检索策略

CSV 数据的检索与叙事文档不同，需要**按场景切换策略**：

```python
class CSVSearchStrategy:
    """
    CSV 按场景切换检索策略
    
    场景矩阵：
    ┌──────────────────────┬──────────────────────┬──────────────────────┐
    │ 查询类型             │ 示例                  │ 检索策略             │
    ├──────────────────────┼──────────────────────┼──────────────────────┤
    │ 精确值查询           │ "user_id=123 的订单"  │ 结构化查询(精确匹配) │
    │ 列级语义查询         │ "找到"状态"列"        │ 列 Embedding 向量检索│
    │ 行级语义查询         │ "金额大于1000的条目"   │ 行 TextUnit 向量检索 │
    │ 跨表关联查询         │ "用户和订单表的关系"   │ 外键关系图遍历       │
    │ 统计聚合查询         │ "有多少种状态?"       │ 列级统计摘要直接返回 │
    └──────────────────────┴──────────────────────┴──────────────────────┘
    """
    
    def search(self, query: str, table_name: str = None,
               top_k: int = 10) -> list[ScoredDoc]:
        """CSV 多模式检索"""
        
        # Step 1: 意图路由 — 判断查询类型
        intent = self._classify_csv_query(query)
        
        if intent == "exact_value":
            return self._exact_value_search(query, table_name)
        elif intent == "column_semantic":
            return self._column_semantic_search(query, top_k)
        elif intent == "row_semantic":
            return self._row_semantic_search(query, table_name, top_k)
        elif intent == "cross_table":
            return self._cross_table_search(query)
        elif intent == "aggregation":
            return self._aggregation_search(query, table_name)
        else:
            # 默认走行级语义
            return self._row_semantic_search(query, table_name, top_k)
    
    def _classify_csv_query(self, query: str) -> str:
        """用 LLM 或规则分类 CSV 查询类型"""
        rules = {
            "exact_value": [r'=\s*\w+', r'等于', r'为\s*\w+$'],
            "column_semantic": [r'列$', r'字段', r'属性', r'column'],
            "aggregation": [r'多少', r'统计', r'分布', r'平均', r'count', r'sum'],
            "cross_table": [r'关系', r'关联', r'联系', r'join', r'relation'],
        }
        for intent, patterns in rules.items():
            if any(re.search(p, query) for p in patterns):
                return intent
        return "row_semantic"
```

### 3.6.5 集成到 DocumentLoader

```python
class DocumentLoader:
    """多格式文档加载 — 已集成 CSV 支持"""
    
    SUPPORTED_FORMATS = {
        ".md":   "markdown",
        ".pdf":  "pdf",
        ".docx": "docx",
        ".txt":  "text",
        ".csv":  "csv",        # ★ 新增
        ".tsv":  "csv",        # 制表符分隔
        ".psv":  "csv",        # 管道符分隔
    }
    
    def load(self, file_path: str) -> list[Document]:
        ext = os.path.splitext(file_path)[1].lower()
        fmt = self.SUPPORTED_FORMATS.get(ext)
        
        if fmt == "csv":
            # CSV 走专用加载器
            csv_loader = CSVLoader()
            csv_table = csv_loader.load(file_path)
            # 将行 Chunk 转为标准 Document 对象供下游 Pipeline 消费
            return [
                Document(
                    text=chunk.text,
                    metadata={
                        "source": file_path,
                        "type": "csv_row",
                        "csv_table": csv_table.filename,
                        "row_index": chunk.row_index,
                    }
                )
                for chunk in csv_table.row_chunks
            ]
        elif fmt in ("markdown", "pdf", "docx", "text"):
            return self._load_document(file_path, fmt)
        else:
            raise UnsupportedFormatError(f"不支持的文件格式: {ext}")
```

---

## 3.7 文件格式扩展：网络资源索引

### 3.7.1 概述

网络资源（Web URL）与本地文件的 GraphRAG 索引共享同一套下游 Pipeline（分块→实体提取→关系提取→社区检测），但在**获取层**需要专门的 Web Loader:

```
网络资源 URL
   │
   ├── 方式 A: 单次抓取 ─────────────────────────────────┐
   │  URL → HTTP GET → HTML → 正文提取(Readability)      │
   │  → Markdown 化 → 走标准 Pipeline                    │
   │                                                    │
   ├── 方式 B: 递归爬取 ─────────────────────────────────┐
   │  Seed URL → 同域发现(爬虫) → 多页面索引              │
   │  → 页面间链接关系 → 跨文档实体融合                   │
   │                                                    │
   └── 方式 C: 定时同步 ─────────────────────────────────┐
       URL + Cron 表达式 → Celery 定时任务               │
       → diff 检测变更 → 增量更新知识图谱                 │
       → 通知订阅者                                      │
```

### 3.7.2 数据模型

```python
# === Web 资源相关数据模型 ===

class WebResource(BaseModel):
    """网络资源元信息"""
    id: str                                           # WR-xxxxxxxx
    url: str
    domain: str
    title: str                                        # <title> 或 H1
    description: str                                  # meta description
    content_type: str                                 # text/html, application/json...
    content_length: int                               # 正文长度(字节)
    fetch_mode: Literal["single", "crawl", "scheduled"]
    
    # 爬取元数据
    crawl_depth: int = 0                              # 当前爬取深度
    same_domain_links: list[str] = []                 # 同域链接
    external_links: list[str] = []                    # 外链
    
    # 时间戳
    fetched_at: str                                   # 首次抓取时间
    last_modified: Optional[str]                      # HTTP Last-Modified
    etag: Optional[str]                               # HTTP ETag（增量检测）
    expires_at: Optional[str]                         # 定时刷新时间
    
    # 关联的文档
    document_ids: list[str] = []                      # 生成的 Document ID 列表
    status: Literal["pending", "indexed", "failed", "expired"]

class CrawlJob(BaseModel):
    """爬虫任务"""
    id: str
    seed_url: str
    max_depth: int                                    # 最大爬取深度
    max_pages: int                                    # 最大页面数
    same_domain_only: bool = True                     # 是否仅限同域
    include_patterns: list[str] = []                  # 包含URL正则
    exclude_patterns: list[str] = []                  # 排除URL正则
    respect_robots_txt: bool = True
    crawl_delay: float = 1.0                          # 爬取延迟(秒)
    status: Literal["running", "completed", "paused", "failed"]
    pages_fetched: int = 0
    pages_total: int = 0
    started_at: Optional[str]
    completed_at: Optional[str]

class ScheduledSync(BaseModel):
    """定时同步配置"""
    id: str
    resource_id: str
    cron_expression: str                              # "0 6 * * 1" 每周一早6点
    last_sync_at: Optional[str]
    next_sync_at: Optional[str]
    notify_on_change: bool = False                    # 变更是否通知
    webhook_url: Optional[str]                        # 变更通知回调
```

### 3.7.3 Web Loader 实现

```python
class WebLoader:
    """
    网络资源加载器
    
    架构：
    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
    │  URL 解析    │ → │  HTTP 抓取   │ → │  正文提取    │
    │  (验证/归一化)│    │  (重试/限流)  │    │  (Readability)│
    └──────────────┘    └──────────────┘    └──────┬───────┘
                                                   │
    ┌──────────────┐    ┌──────────────┐           │
    │  Markdown 化  │ ← │  元数据提取  │ ←─────────┘
    │  (HTML→MD)   │    │  (标题/描述/  │
    └──────┬───────┘    │   last-mod)  │
           │            └──────────────┘
           ▼
    ┌──────────────┐
    │  Document    │ → 标准 Pipeline（分块→实体→关系→社区）
    │  输出         │
    └──────────────┘
    """
    
    def __init__(self):
        self.session = self._create_session()
        self.readability = Readability()              # python-readability
        self.html2text = Html2Text()                  # html2text
    
    def _create_session(self) -> requests.Session:
        """创建带重试和限流的 HTTP Session"""
        session = requests.Session()
        
        # 重试策略
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 浏览器 UA 避免被屏蔽
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (compatible; PRD2TechSpec-Bot/1.0; "
                "+https://prd2techspec.com/bot)"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        
        return session
    
    def fetch_page(self, url: str) -> WebResource:
        """
        抓取单个页面并转为 Document
        
        流程：
        1. URL 验证 + 归一化
        2. HTTP GET（带重试）
        3. 检查 Content-Type（只处理 text/html）
        4. 正文提取（Readability）
        5. Markdown 转换
        6. 元数据提取
        7. 返回 WebResource + Document
        """
        # Step 1: URL 归一化
        url = self._normalize_url(url)
        self._validate_url(url)
        
        # Step 2: HTTP GET
        response = self._http_get(url)
        
        # Step 3: Content-Type 校验
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            # 非 HTML 内容（JSON/XML/纯文本）走另一条路
            return self._handle_non_html(response, url)
        
        # Step 4: 正文提取（Readability）
        doc = self.readability.parse(response.text)
        if not doc or not doc.content:
            raise WebExtractionError(f"无法从 {url} 提取正文内容")
        
        # Step 5: HTML → Markdown
        self.html2text.body_width = 0  # 不自动换行
        markdown_content = self.html2text.handle(doc.content)
        
        # Step 6: 提取同域/外链
        soup = BeautifulSoup(response.text, "html.parser")
        same_domain = self._extract_links(soup, url, same_domain_only=True)
        external = self._extract_links(soup, url, same_domain_only=False)
        
        # Step 7: 构造 WebResource
        resource = WebResource(
            id=f"WR-{str(uuid4())[:8]}",
            url=url,
            domain=urlparse(url).netloc,
            title=doc.title or "",
            description=self._extract_meta_description(soup),
            content_type=content_type,
            content_length=len(markdown_content),
            fetch_mode="single",
            same_domain_links=same_domain,
            external_links=external,
            fetched_at=datetime.utcnow().isoformat(),
            last_modified=response.headers.get("Last-Modified"),
            etag=response.headers.get("ETag"),
            status="indexed",
        )
        
        # Step 8: 转为标准 Document 对象
        document = Document(
            text=markdown_content,
            metadata={
                "source": url,
                "source_type": "web_page",
                "title": doc.title,
                "resource_id": resource.id,
                "domain": resource.domain,
                "fetched_at": resource.fetched_at,
            }
        )
        
        # Step 9: 写入存储
        self._store_resource(resource)
        self._store_document(document)
        
        resource.document_ids = [document.id]
        return resource
    
    def _normalize_url(self, url: str) -> str:
        """URL 归一化 — 补全 scheme、去锚点、规范化"""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        parsed = urlparse(url)
        # 移除 URL 片段（#fragment）
        normalized = parsed._replace(fragment="").geturl()
        # 移除尾部斜杠（保留路径含义）
        if normalized.endswith("/") and parsed.path != "/":
            normalized = normalized.rstrip("/")
        
        return normalized
    
    def _validate_url(self, url: str):
        """URL 校验"""
        parsed = urlparse(url)
        if not parsed.netloc:
            raise InvalidURLError(f"无效 URL: {url}")
        
        # 黑名单过滤
        blocked_domains = [
            "localhost", "127.0.0.1", "0.0.0.0",
            "10.", "172.16.", "192.168.",           # 内网
        ]
        for blocked in blocked_domains:
            if parsed.netloc.startswith(blocked) or parsed.netloc == blocked:
                raise SecurityError(f"禁止访问内网地址: {url}")
    
    def _http_get(self, url: str) -> requests.Response:
        """HTTP GET 带超时和重试"""
        try:
            response = self.session.get(
                url,
                timeout=(5, 30),    # connect=5s, read=30s
                allow_redirects=True,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise WebFetchError(f"请求超时: {url}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                raise WebForbiddenError(f"被拒绝访问: {url}")
            elif e.response.status_code == 404:
                raise WebNotFoundError(f"页面不存在: {url}")
            raise
    
    def _handle_non_html(self, response: requests.Response,
                          url: str) -> WebResource:
        """处理非 HTML 内容（JSON API / 纯文本等）"""
        content_type = response.headers.get("Content-Type", "").lower()
        
        if "json" in content_type:
            # JSON API → 转为 Markdown 表格
            data = response.json()
            markdown = self._json_to_markdown(data)
        elif "text/plain" in content_type:
            # 纯文本 → 直接使用
            markdown = response.text
        else:
            raise UnsupportedContentTypeError(f"不支持的内容类型: {content_type}")
        
        # 后续流程同 HTML...
        return self._build_resource(url, response, markdown, content_type)
    
    def _json_to_markdown(self, data: Any, level: int = 1) -> str:
        """JSON → Markdown 递归转换"""
        if isinstance(data, dict):
            lines = []
            for key, val in data.items():
                if isinstance(val, (dict, list)):
                    lines.append(f"{'#' * min(level, 6)} {key}")
                    lines.append(self._json_to_markdown(val, level + 1))
                else:
                    lines.append(f"- **{key}**: {val}")
            return "\n".join(lines)
        elif isinstance(data, list):
            lines = []
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    lines.append(f"##### 条目 {i+1}")
                    lines.append(self._json_to_markdown(item, level + 1))
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)
        else:
            return str(data)
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str,
                       same_domain_only: bool) -> list[str]:
        """提取页面中的所有链接"""
        base_domain = urlparse(base_url).netloc
        links = set()
        
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            # 跳过空链接、javascript:、mailto:
            if not href or href.startswith(("javascript:", "mailto:", "#")):
                continue
            
            # 解析绝对 URL
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            
            # 只保留 http/https
            if parsed.scheme not in ("http", "https"):
                continue
            
            # 按同域/外链过滤
            if same_domain_only:
                if parsed.netloc == base_domain:
                    links.add(self._normalize_url(absolute))
            else:
                if parsed.netloc != base_domain:
                    links.add(self._normalize_url(absolute))
        
        return list(links)[:100]  # 最多取100个链接
    
    def _extract_meta_description(self, soup: BeautifulSoup) -> str:
        """提取 meta description"""
        meta = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", attrs={"property": "og:description"})
        )
        return meta.get("content", "") if meta else ""
```

### 3.7.4 爬虫实现（方式 B：递归爬取）

```python
class WebCrawler:
    """
    同域递归爬虫 — 从 Seed URL 出发发现并索引关联页面
    
    爬取策略：
    1. BFS 遍历（按深度 layer 逐层扩展）
    2. URLs 去重（基于归一化后的 URL）
    3. 遵守 robots.txt
    4. 爬取延迟控制（礼貌爬取）
    5. 并发控制（asyncio + Semaphore）
    6. 断点续爬（Redis 记录已爬/待爬队列）
    """
    
    def __init__(self):
        self.loader = WebLoader()
        self.redis_client = redis.from_url(settings.REDIS_URL)
        self.robots_cache: dict[str, RobotsParser] = {}
    
    async def crawl(self, job: CrawlJob) -> CrawlJob:
        """执行爬取任务"""
        start_time = datetime.utcnow()
        job.status = "running"
        job.started_at = start_time.isoformat()
        
        # 初始化队列
        seed_url = self.loader._normalize_url(job.seed_url)
        seen_urls: set[str] = set()
        
        # BFS 层级队列: {depth: [urls]}
        queue: dict[int, list[str]] = {0: [seed_url]}
        seen_urls.add(seed_url)
        
        semaphore = asyncio.Semaphore(5)  # 最大并发 5
        
        async def fetch_with_limit(url: str, depth: int):
            async with semaphore:
                try:
                    # 尊重 robots.txt
                    if job.respect_robots_txt and not self._can_fetch(url):
                        return None
                    
                    resource = self.loader.fetch_page(url)
                    
                    # 如果还没达到最大页面数，从页面发现新链接
                    if (depth < job.max_depth 
                        and len(seen_urls) < job.max_pages
                        and resource.same_domain_links):
                        
                        new_links = [
                            l for l in resource.same_domain_links
                            if l not in seen_urls
                            and self._matches_patterns(l, job)
                        ]
                        
                        # 限制每层新增数量
                        max_new = min(
                            job.max_pages - len(seen_urls),
                            len(new_links)
                        )
                        new_links = new_links[:max_new]
                        
                        if new_links:
                            next_depth = depth + 1
                            if next_depth not in queue:
                                queue[next_depth] = []
                            queue[next_depth].extend(new_links)
                            seen_urls.update(new_links)
                    
                    # 爬取延迟
                    await asyncio.sleep(job.crawl_delay)
                    
                    return resource
                    
                except Exception as e:
                    logger.warning(f"爬取失败 {url}: {e}")
                    return None
        
        # BFS 主循环
        current_depth = 0
        while current_depth <= job.max_depth and len(seen_urls) < job.max_pages:
            urls_at_depth = queue.get(current_depth, [])
            if not urls_at_depth:
                current_depth += 1
                continue
            
            # 并发抓取该层所有 URL
            tasks = [
                fetch_with_limit(url, current_depth)
                for url in urls_at_depth
            ]
            results = await asyncio.gather(*tasks)
            
            job.pages_fetched += len([r for r in results if r is not None])
            current_depth += 1
            
            # 更新 Redis 断点
            self._save_checkpoint(job.id, seen_urls, queue, current_depth)
        
        job.status = "completed"
        job.completed_at = datetime.utcnow().isoformat()
        job.pages_total = len(seen_urls)
        return job
    
    def _can_fetch(self, url: str) -> bool:
        """检查 robots.txt 是否允许抓取"""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        if base not in self.robots_cache:
            rp = RobotsParser()
            try:
                resp = requests.get(
                    f"{base}/robots.txt",
                    timeout=5,
                    headers={"User-Agent": "PRD2TechSpec-Bot/1.0"},
                )
                rp.parse(resp.text)
            except Exception:
                # 无法获取 robots.txt 时默认允许
                rp.allow_all = True
            self.robots_cache[base] = rp
        
        return self.robots_cache[base].can_fetch(
            "PRD2TechSpec-Bot/1.0", url
        )
    
    def _matches_patterns(self, url: str, job: CrawlJob) -> bool:
        """检查 URL 是否匹配 include/exclude 模式"""
        if job.include_patterns:
            if not any(re.search(p, url) for p in job.include_patterns):
                return False
        if job.exclude_patterns:
            if any(re.search(p, url) for p in job.exclude_patterns):
                return False
        return True
    
    def _save_checkpoint(self, job_id: str, seen: set,
                         queue: dict, depth: int):
        """保存爬取断点到 Redis"""
        checkpoint = {
            "seen_urls": list(seen),
            "queue": {str(k): v for k, v in queue.items()},
            "current_depth": depth,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.redis_client.setex(
            f"crawl:checkpoint:{job_id}",
            86400,  # 24h 过期
            json.dumps(checkpoint),
        )
```

### 3.7.5 定时同步（方式 C：Scheduled Sync）

```python
class WebSyncScheduler:
    """
    定时同步 — 定期检查 URL 变更，增量更新知识图谱
    
    变更检测策略：
    1. HTTP ETag / Last-Modified 头（最优先）
    2. 内容哈希对比（SHA256 of Markdown）
    3. 结构差异对比（实体/关系变化量）
    """
    
    def __init__(self):
        self.loader = WebLoader()
        self.graph_store = Neo4jGraphStore()
    
    @celery.task(bind=True, max_retries=3)
    def sync_resource(self, resource_id: str):
        """单资源同步任务"""
        resource = self.resource_store.get(resource_id)
        if not resource:
            return {"status": "not_found"}
        
        # 1. 快速检测：ETag / Last-Modified
        head_resp = requests.head(resource.url, timeout=10)
        
        if resource.etag and head_resp.headers.get("ETag") == resource.etag:
            return {"status": "unchanged", "method": "etag"}
        
        if resource.last_modified:
            lm = head_resp.headers.get("Last-Modified")
            if lm and lm == resource.last_modified:
                return {"status": "unchanged", "method": "last_modified"}
        
        # 2. 重新抓取
        new_resource = self.loader.fetch_page(resource.url)
        
        # 3. 内容哈希对比
        if new_resource.content_length == resource.content_length:
            # 完整哈希对比（仅在长度相同时执行，避免大文件多次读）
            if self._content_hash_matches(new_resource, resource):
                # 更新元数据但不触发索引重建
                self.resource_store.update_timestamp(resource_id)
                return {"status": "unchanged", "method": "hash"}
        
        # 4. 检测到变更 → 重新走完整 Pipeline
        updated_docs = self._reindex_resource(new_resource)
        
        # 5. 发送变更通知
        if resource.notify_on_change:
            self._send_change_notification(resource, new_resource)
        
        return {
            "status": "updated",
            "old_content_length": resource.content_length,
            "new_content_length": new_resource.content_length,
            "documents_reindexed": len(updated_docs),
        }
    
    def schedule_sync(self, resource_id: str, 
                      cron_expression: str) -> ScheduledSync:
        """配置定时同步"""
        sync = ScheduledSync(
            id=str(uuid4()),
            resource_id=resource_id,
            cron_expression=cron_expression,
            last_sync_at=datetime.utcnow().isoformat(),
            next_sync_at=self._calculate_next_run(cron_expression),
        )
        # 注册到 Celery Beat
        self._register_beat_task(sync)
        return sync
    
    def _calculate_next_run(self, cron_expr: str) -> str:
        """计算下次执行时间"""
        from croniter import croniter
        from datetime import datetime
        cron = croniter(cron_expr, datetime.utcnow())
        return cron.get_next(datetime).isoformat()
```

### 3.7.6 Web Loader 检索增强

当用户查询涉及网络资源时，检索策略需扩展：

```python
class WebAugmentedSearchMixin:
    """
    网络资源增强检索 — 融合 Web 资源进入标准检索流程
    
    检索路由扩展（更新 Intent Router）：
    
    查询类型: "查询最近的技术动态/文档"
    → Intent Router 检测到 "实时性需求" 
    → 如果知识图谱中无匹配（或匹配度低）
    → 触发 Web Search Fallback:
        1. 用 LLM 生成搜索关键词
        2. 调网络搜索 API（如 SearXNG / Bing API）
        3. 抓取搜索结果页
        4. 实时索引并返回
        5. 可选：持久化到知识图谱
    """
    
    def web_fallback_search(self, query: str) -> list[ScoredDoc]:
        """当本地知识图谱命中不足时，回退到网络搜索"""
        
        # Step 1: 检查本地检索质量
        local_results = self.pipeline.retrieve(query, top_k=5)
        if self._is_sufficient(local_results):
            return local_results  # 本地够用，不触发网络
        
        # Step 2: 生成搜索关键词
        keywords = self.llm.complete(f"""
        将以下查询改写为 2-3 条网络搜索关键词（用于搜索引擎）：
        查询：{query}
        
        输出 JSON 列表：["关键词1", "关键词2"]
        """, response_format={"type": "json_object"})
        
        search_queries = json.loads(keywords.text)
        
        # Step 3: 调用搜索引擎（SearXNG / Bing API）
        web_results = []
        for kw in search_queries:
            results = self.web_search_api.search(kw, top_k=3)
            web_results.extend(results)
        
        # Step 4: 抓取并实时索引（仅 Top 结果）
        fetched_docs = []
        for result in web_results[:3]:  # 最多实时索引3个
            try:
                resource = self.web_loader.fetch_page(result.url)
                fetched_docs.append(resource)
            except Exception as e:
                logger.warning(f"实时索引失败 {result.url}: {e}")
        
        # Step 5: 融合本地 + 网络结果
        all_results = list(local_results)
        for doc in fetched_docs:
            all_results.append(ScoredDoc(
                id=doc.id,
                text=f"# {doc.title}\\n\\n{doc.description}" 
                     if doc.description else doc.url,
                score=0.5,  # 网络结果初始分低一些
                source="web",
                metadata={"url": doc.url, "title": doc.title},
            ))
        
        return all_results[:top_k]
```

---

## 四、Layer 2: Analysis Layer — 文档分析 Agent

### 4.1 Agent Graph 结构

```python
class AnalysisState(TypedDict):
    prd_raw: str
    prd_sections: list[DocumentSection]     # 分节结果
    extracted_requirements: list[Requirement]
    extracted_entities: list[KGEntity]       # 待同步到知识层
    extracted_constraints: list[Constraint]
    dependency_graph: DependencyGraph
    domain_tags: list[str]
    clarification_questions: list[str]       # 需要追问的问题
    analysis_result: AnalysisResult
    confidence: float

analysis_graph = StateGraph(AnalysisState)

analysis_graph.add_node("document_parser", DocumentParserNode())
analysis_graph.add_node("requirement_extractor", RequirementExtractorNode())
analysis_graph.add_node("entity_extractor", AnalysisEntityExtractorNode())
analysis_graph.add_node("constraint_analyzer", ConstraintAnalyzerNode())
analysis_graph.add_node("dependency_analyzer", DependencyAnalyzerNode())
analysis_graph.add_node("domain_classifier", DomainClassifierNode())
analysis_graph.add_node("result_assembler", AnalysisResultAssemblerNode())
analysis_graph.add_node("clarity_checker", ClarityCheckerNode())  # 检查是否清晰

analysis_graph.set_entry_point("document_parser")
analysis_graph.add_edge("document_parser", "requirement_extractor")
analysis_graph.add_edge("requirement_extractor", "entity_extractor")
analysis_graph.add_edge("entity_extractor", "constraint_analyzer")
analysis_graph.add_edge("constraint_analyzer", "dependency_analyzer")
analysis_graph.add_edge("dependency_analyzer", "domain_classifier")
analysis_graph.add_edge("domain_classifier", "clarity_checker")

# 如果信息不清晰，追问用户
analysis_graph.add_conditional_edges(
    "clarity_checker",
    needs_clarification,
    {True: "result_assembler", False: "result_assembler"}
    # 追问信息会通过 HumanReviewNode 在 Orchestrator 层处理
)

analysis_graph.add_edge("result_assembler", END)
```

### 4.2 各节点详细设计

#### 4.2.1 DocumentParserNode

```python
class DocumentParserNode:
    """将 PRD 文档解析为结构化章节"""
    
    def run(self, state: AnalysisState) -> AnalysisState:
        raw = state.prd_raw
        
        # 1. 文档类型检测
        doc_type = self.detect_type(state.prd_file_type)
        
        # 2. 按章节/标题拆分
        if doc_type == "markdown":
            sections = self.parse_markdown(raw)
        elif doc_type == "pdf":
            sections = self.parse_pdf(raw)  # 调用 Unstructured/Docling
        elif doc_type == "docx":
            sections = self.parse_docx(raw)
        else:
            sections = self.parse_plain_text(raw)
        
        # 3. 识别章节类型
        SECTION_TYPES = ["background", "goal", "scope", 
                        "functional_req", "non_functional_req",
                        "constraints", "stakeholders", "milestones"]
        
        classified = []
        for sec in sections:
            sec_type = self.classify_section(sec.title, sec.content)
            classified.append(DocumentSection(
                title=sec.title,
                content=sec.content,
                section_type=sec_type,
                level=sec.level,
            ))
        
        state.prd_sections = classified
        return state
    
    def classify_section(self, title: str, content: str) -> str:
        """用 LLM 或规则匹配判断章节类型"""
        # 先用关键词规则快速匹配
        rules = {
            "functional_req": ["功能需求", "功能要求", "functional"],
            "non_functional_req": ["非功能", "性能要求", "non-functional"],
            "constraints": ["约束", "限制", "限制条件"],
            "background": ["背景", "现状", "当前"],
            "goal": ["目标", "目的", "愿景"],
        }
        for sec_type, keywords in rules.items():
            if any(kw in title.lower() or kw in content[:200].lower() 
                   for kw in keywords):
                return sec_type
        
        # 规则没命中则用 LLM
        result = self.llm.complete(f"""
        判断以下文档章节的类型，从以下列表中选择一个最匹配的：
        {list(rules.keys())}
        
        标题：{title}
        内容前200字：{content[:200]}
        
        只输出类型名称。
        """)
        return result.text.strip()
```

#### 4.2.2 RequirementExtractorNode

```python
class RequirementExtractorNode:
    """
    从 PRD 中提取结构化需求
    这是分析层最关键的一步
    """
    
    REQUIREMENT_EXTRACT_PROMPT = """
    你是一个PRD需求分析专家。请从以下PRD内容中提取所有需求。
    
    每个需求需要包含：
    - id: 唯一标识（FR-001, FR-002... 或 NFR-001...）
    - type: functional / non_functional
    - category: 对于功能需求：用户管理/订单处理/数据报表... 
                对于非功能需求：性能/安全/可用性/可扩展性...
    - priority: P0(关键) / P1(重要) / P2(一般) / P3(可延后)
    - description: 需求详细描述
    - actor: 执行者（用户/管理员/系统）
    - acceptance_criteria: 验收标准（如果有）
    - source_section: 来自 PRD 的哪个章节
    
    请严格输出 JSON 格式的列表。
    不要遗漏任何需求，也不要凭空捏造。
    
    PRD 内容：
    {prd_content}
    """
    
    def run(self, state: AnalysisState) -> AnalysisState:
        all_requirements = []
        
        # 提取功能需求
        func_sections = [s for s in state.prd_sections 
                        if s.section_type == "functional_req"]
        for section in func_sections:
            result = self.llm.complete(
                self.REQUIREMENT_EXTRACT_PROMPT.format(
                    prd_content=section.content
                ),
                response_format={"type": "json_object"}
            )
            reqs = self.parse_requirements(result.text, "functional", section.title)
            all_requirements.extend(reqs)
        
        # 提取非功能需求
        nfunc_sections = [s for s in state.prd_sections 
                         if s.section_type == "non_functional_req"]
        for section in nfunc_sections:
            result = self.llm.complete(
                self.REQUIREMENT_EXTRACT_PROMPT.format(
                    prd_content=section.content
                ),
                response_format={"type": "json_object"}
            )
            reqs = self.parse_requirements(result.text, "non_functional", section.title)
            all_requirements.extend(reqs)
        
        state.extracted_requirements = all_requirements
        return state
    
    def parse_requirements(self, llm_output: str, req_type: str, 
                          source: str) -> list[Requirement]:
        """解析 LLM 输出的 JSON"""
        data = json.loads(llm_output)
        return [Requirement(
            id=item.get("id", f"{'FR' if req_type=='functional' else 'NFR'}-{i+1:03d}"),
            type=req_type,
            category=item.get("category", "general"),
            priority=item.get("priority", "P2"),
            description=item["description"],
            actor=item.get("actor", "system"),
            acceptance_criteria=item.get("acceptance_criteria", []),
            source_section=source,
        ) for i, item in enumerate(data.get("requirements", data))]
```

#### 4.2.3 ConstraintAnalyzerNode

```python
class ConstraintAnalyzerNode:
    """
    提取约束条件，包括：
    - 技术约束（必须用某技术栈）
    - 性能约束（QPS、响应时间）
    - 时间约束（交付时间）
    - 预算约束
    - 合规约束（安全等级、数据合规）
    - 团队约束（团队技术栈、人员规模）
    """
    
    CONSTRAINT_PROMPT = """
    从以下 PRD 内容中提取所有约束条件。
    
    约束类型：
    - technical: 技术栈/平台/版本限制
    - performance: QPS/响应时间/吞吐量
    - time: 交付时间/里程碑
    - budget: 预算/成本限制
    - compliance: 安全/合规/审计要求
    - team: 团队技能/人数/组织结构
    - integration: 需对接的外部系统/接口
    - scale: 用户规模/数据规模
    
    PRD 内容：
    {prd_content}
    
    已提取的需求列表（供参考上下文）：
    {requirements}
    
    输出 JSON 格式：
    [{{
        "type": "technical",
        "description": "必须使用 Java 17 + Spring Boot 3.x",
        "severity": "must",  # must/should/could
        "source_section": "技术约束",
        "related_requirements": ["FR-001", "FR-005"]
    }}]
    """
    
    def run(self, state: AnalysisState) -> AnalysisState:
        # 从所有章节中提取约束
        all_content = "\n\n".join([s.content for s in state.prd_sections])
        reqs_summary = "\n".join([
            f"{r.id}: {r.description}" 
            for r in state.extracted_requirements
        ])
        
        result = self.llm.complete(
            self.CONSTRAINT_PROMPT.format(
                prd_content=all_content,
                requirements=reqs_summary,
            ),
            response_format={"type": "json_object"}
        )
        constraints = json.loads(result.text)
        state.extracted_constraints = [Constraint(**c) for c in constraints]
        return state
```

#### 4.2.4 DependencyAnalyzerNode

```python
class DependencyAnalyzerNode:
    """
    分析需求之间的依赖关系：
    - 顺序依赖：需求A必须在需求B之前完成
    - 阻塞依赖：需求A阻塞需求B
    - 关联依赖：需求A和B需要同时设计
    - 互斥依赖：需求A和B冲突
    """
    
    DEPENDENCY_PROMPT = """
    分析以下需求列表之间的依赖关系。
    
    需求列表：
    {requirements}
    
    关系类型：
    - blocks: A阻塞B（必须先做A再做B）
    - relates: A和B相关（需要一起设计）
    - duplicates: A和B重复
    - conflicts: A和B冲突（不能同时实现）
    - refines: A是B的细化（B是抽象需求，A是具体实现）
    
    输出 JSON 格式：
    [{{
        "source_id": "FR-001",
        "target_id": "FR-005",
        "relation": "blocks",
        "reason": "必须先完成用户认证模块，才能实现权限管理"
    }}]
    
    如果没有依赖关系就输出空列表。
    """
    
    def run(self, state: AnalysisState) -> AnalysisState:
        reqs_text = "\n".join([
            f"{r.id}[{r.priority}]: {r.description} ({r.category})"
            for r in state.extracted_requirements
        ])
        
        result = self.llm.complete(
            self.DEPENDENCY_PROMPT.format(requirements=reqs_text),
            response_format={"type": "json_object"}
        )
        deps = json.loads(result.text)
        state.dependency_graph = DependencyGraph(
            nodes=state.extracted_requirements,
            edges=[Dependency(**d) for d in deps]
        )
        return state
```

#### 4.2.5 AnalysisResult 输出模型

```python
class AnalysisResult(BaseModel):
    """分析层最终输出"""
    
    # 基本信息
    project_name: str
    summary: str                              # PRD 摘要
    domain_tags: list[str]                    # 领域标签（用于知识检索）
    
    # 需求
    requirements: list[Requirement]
    requirement_count: int
    priority_distribution: dict[str, int]      # P0: 3, P1: 8...
    category_distribution: dict[str, int]      # 功能分类统计
    
    # 约束
    constraints: list[Constraint]
    critical_constraints: list[Constraint]     # severity=must 的
    
    # 依赖
    dependency_graph: DependencyGraph
    
    # 实体
    entities: list[KGEntity]                   # 提取的实体（待同步Knowledge Layer）
    
    # 风险
    initial_risks: list[Risk]
    
    # 元信息
    confidence: float                          # 分析置信度
    sections_analyzed: int                     # 分析章节数
    missing_sections: list[str]               # 缺失的章节类型
    clarification_questions: list[str]        # 需要追问的问题
    
    class Requirement(BaseModel):
        id: str
        type: Literal["functional", "non_functional"]
        category: str
        priority: Literal["P0", "P1", "P2", "P3"]
        description: str
        actor: str
        acceptance_criteria: list[str] = []
        source_section: str
    
    class Constraint(BaseModel):
        type: str
        description: str
        severity: Literal["must", "should", "could"]
        source_section: str
        related_requirements: list[str] = []
    
    class Dependency(BaseModel):
        source_id: str
        target_id: str
        relation: Literal["blocks", "relates", "duplicates", "conflicts", "refines"]
        reason: str
    
    class DependencyGraph(BaseModel):
        nodes: list[Requirement]
        edges: list[Dependency]
        
        def to_mermaid(self) -> str:
            """生成 Mermaid 依赖图"""
            lines = ["graph TD"]
            for edge in self.edges:
                lines.append(f"    {edge.source_id}-->{edge.source_id.replace('FR','NFR')}_{edge.relation}-->{edge.target_id}")
            return "\n".join(lines)
```

### 4.3 Analysis Layer 补充节点

#### 4.3.1 多语言 PRD 支持

```python
class LanguageDetectorNode:
    """
    自动检测 PRD 语言，按语言分模式处理
    支持：中文、英文、日文、中英混合
    """
    
    def detect_language(self, text: str) -> str:
        """检测语言并判断是否需要翻译"""
        # 统计字符分布
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        total = len(text.strip())
        
        if chinese_chars / total > 0.3:
            return "zh"
        elif english_chars / total > 0.5:
            return "en"
        elif chinese_chars > 0 and english_chars > 0:
            return "zh_en_mix"
        return "en"
    
    def run(self, state: AnalysisState) -> AnalysisState:
        lang = self.detect_language(state.prd_raw)
        state.language = lang
        
        if lang == "en":
            # 英文PRD → 翻译为中文以使用后续中文知识图谱
            state.prd_translated = self.translate_to_zh(state.prd_raw)
            state.planning_notes.append("PRD为英文，已自动翻译为中文处理")
        elif lang == "zh_en_mix":
            # 中英混合 → 提取英文部分翻译
            state.prd_translated = self.normalize_mix_language(state.prd_raw)
        
        return state
```

#### 4.3.2 需求质量评分

```python
class RequirementQualityNode:
    """
    对每条需求进行质量评分
    维度：完整性、清晰度、可测试性、一致性、必要性、可行性
    """
    
    QUALITY_PROMPT = """
    评价以下 PRD 需求的撰写质量。
    
    需求：{req_id}: {description}
    验收标准：{acceptance_criteria}
    优先级：{priority}
    所属章节：{section}
    
    请从以下维度评分（1-5分）：
    
    1. 完整性（Completeness）
       - 5: 描述了完整的功能链路，有明确的输入输出
       - 3: 描述了主要功能，但缺少边界条件
       - 1: 只有一句话描述
       
    2. 清晰度（Clarity）
       - 5: 无歧义、无模糊用词（"高性能"→"99.9%可用性"）
       - 3: 少量模糊用词
       - 1: 大量模糊表述
       
    3. 可测试性（Testability）
       - 5: 有明确的验收标准和量化指标
       - 3: 部分可验证
       - 1: 无法验证
       
    4. 一致性（Consistency）
       - 5: 与其它需求完全一致
       - 3: 存在潜在冲突
       - 1: 明显矛盾
       
    5. 必要性（Necessity）
       - 5: 核心业务需求，不可或缺
       - 3: 锦上添花的功能
       - 1: 可有可无
       
    6. 可行性（Feasibility）
       - 5: 在当前约束下完全可行
       - 3: 有挑战但可实现
       - 1: 在当前约束下不可行
    
    输出 JSON：
    {{
        "req_id": "FR-001",
        "scores": {{
            "completeness": 4,
            "clarity": 3,
            "testability": 2,
            "consistency": 5,
            "necessity": 5,
            "feasibility": 4
        }},
        "overall_quality": 3.8,
        "issues": [
            {{"dimension": "clarity", "description": "使用了模糊表述'高性能'", "suggestion": "建议替换为具体的QPS指标"}},
            {{"dimension": "testability", "description": "缺少验收标准", "suggestion": "补充具体的验收条件"}}
        ],
        "suggested_improvement": "建议补充性能量化指标和验收标准"
    }}
    """
    
    def run(self, state: AnalysisState) -> AnalysisState:
        quality_scores = []
        
        for req in state.extracted_requirements:
            result = self.llm.complete(
                self.QUALITY_PROMPT.format(
                    req_id=req.id,
                    description=req.description,
                    acceptance_criteria="; ".join(req.acceptance_criteria) or "无",
                    priority=req.priority,
                    section=req.source_section,
                ),
                response_format={"type": "json_object"}
            )
            quality_scores.append(json.loads(result.text))
        
        state.requirement_quality = quality_scores
        state.planning_notes.append(
            f"需求质量评分完成，平均分: "
            f"{sum(q['overall_quality'] for q in quality_scores) / len(quality_scores):.2f}"
        )
        return state
```

#### 4.3.3 项目规模与工作量估算

```python
class EffortEstimatorNode:
    """
    根据需求数量、复杂度、约束条件估算开发工作量
    使用 COCOMO II 模型 + LLM 调整
    """
    
    EFFORT_PROMPT = """
    你是一个项目管理专家。根据以下信息估算开发工作量。
    
    ## 需求统计
    - 功能需求总数：{func_count} (P0: {p0_count}, P1: {p1_count}, P2+: {p2_count})
    - 非功能需求总数：{nfr_count}
    
    ## 技术复杂度因素
    - 技术栈：{tech_stack_description}
    - 集成外部系统数：{integration_count}
    - 数据迁移需求：{has_migration}
    
    ## 团队因素
    - 团队规模假设：{team_size} 人
    - 团队对该技术栈的熟悉度：{familiarity} (1-5)
    
    ## 约束条件
    - 关键约束：{critical_constraints}
    
    请估算：
    1. 总工作量（人月）
    2. 各项分布（前端/后端/数据/运维/测试/管理）
    3. 建议团队规模
    4. 建议工期（月）
    5. 关键路径说明
    6. 风险调整系数
    
    输出 JSON：
    {{
        "total_effort_person_month": 24.5,
        "distribution": {{
            "backend": 12.0,
            "frontend": 4.0,
            "data": 3.0,
            "devops": 2.0,
            "testing": 2.5,
            "management": 1.0
        }},
        "suggested_team_size": 6,
        "suggested_duration_months": 4,
        "critical_path": "用户认证 → 订单服务 → 支付集成 → 报表",
        "risk_factor": 1.2,
        "confidence": "medium",
        "assumptions": ["团队对Spring Boot熟悉", "有现成的基础设施"],
        "notes": ["建议分两期交付以降低风险"]
    }}
    """
    
    def run(self, state: AnalysisState) -> AnalysisState:
        # 准备输入数据
        func_reqs = [r for r in state.extracted_requirements if r.type == "functional"]
        # 调用LLM估算
        result = self.llm.complete(
            self.EFFORT_PROMPT.format(
                func_count=len(func_reqs),
                p0_count=len([r for r in func_reqs if r.priority == "P0"]),
                p1_count=len([r for r in func_reqs if r.priority == "P1"]),
                p2_count=len([r for r in func_reqs if r.priority in ("P2", "P3")]),
                nfr_count=len([r for r in state.extracted_requirements if r.type == "non_functional"]),
                # ... 其他参数
            ),
            response_format={"type": "json_object"}
        )
        state.effort_estimation = json.loads(result.text)
        return state
```

#### 4.3.4 利益相关者分析

```python
class StakeholderAnalyzerNode:
    """
    提取 PRD 中的干系人及其关注点
    """
    
    STAKEHOLDER_PROMPT = """
    从以下 PRD 内容中提取所有利益相关者（干系人）。
    
    PRD 内容：
    {prd_content}
    
    对于每个利益相关者，提取：
    - name: 名称
    - type: 类型（业务方/产品/技术/运营/管理层/外部客户）
    - concerns: 核心关注点
    - expectations: 期望
    - influence: 影响力（高/中/低）
    - interest: 关注度（高/中/低）
    
    输出 JSON 列表。
    """
    
    def run(self, state: AnalysisState) -> AnalysisState:
        result = self.llm.complete(
            self.STAKEHOLDER_PROMPT.format(prd_content=state.prd_raw[:8000]),
            response_format={"type": "json_object"}
        )
        state.stakeholders = json.loads(result.text)
        return state
```

#### 4.3.5 AnalysisState 补充字段

```python
class AnalysisState(TypedDict):
    # ... 原有字段 ...
    
    # --- 新增字段 ---
    language: str                              # 检测到的PRD语言
    prd_translated: Optional[str]              # 翻译后的PRD
    requirement_quality: list[dict]            # 需求质量评分
    effort_estimation: dict                    # 工作量估算
    stakeholders: list[dict]                   # 利益相关者
```

分析层 Graph 增加对应节点：

```python
analysis_graph.add_node("lang_detector", LanguageDetectorNode())
analysis_graph.add_node("quality_scorer", RequirementQualityNode())
analysis_graph.add_node("effort_estimator", EffortEstimatorNode())
analysis_graph.add_node("stakeholder_analyzer", StakeholderAnalyzerNode())

# 新流程：语言检测 → 原有流程 → 质量评分 → 工作量估算
analysis_graph.add_edge("document_parser", "lang_detector")
analysis_graph.add_edge("lang_detector", "requirement_extractor")
analysis_graph.add_edge("clarity_checker", "quality_scorer")
analysis_graph.add_edge("quality_scorer", "effort_estimator")
analysis_graph.add_edge("effort_estimator", "stakeholder_analyzer")
analysis_graph.add_edge("stakeholder_analyzer", "result_assembler")
```

---

## 五、Layer 3: Planning Layer — 架构规划 Agent

### 5.1 Agent Graph 结构

```python
class PlanningState(TypedDict):
    analysis_result: AnalysisResult            # 来自 Layer 2
    knowledge_context: RetrievalContext         # 来自 Layer 1
    architecture_patterns: list[PatternEval]    # 候选架构模式
    selected_pattern: ArchitecturePattern
    tech_stack_choices: list[TechChoice]        # 技术栈选型
    component_decomposition: list[Component]    # 组件分解
    data_architecture: DataArchitecture         # 数据架构
    api_design: APIDesign                       # API 概览
    deployment_plan: DeploymentPlan             # 部署方案
    planning_result: PlanningResult
    planning_notes: list[str]                   # 规划过程中的思考记录

planning_graph = StateGraph(PlanningState)

planning_graph.add_node("knowledge_augment", KnowledgeAugmentNode())     # 补充知识
planning_graph.add_node("pattern_recommend", PatternRecommendNode())     # 架构模式推荐
planning_graph.add_node("pattern_confirm", PatternConfirmNode())         # 模式确认
planning_graph.add_node("tech_stack_select", TechStackSelectNode())      # 技术栈选型
planning_graph.add_node("component_decompose", ComponentDecomposeNode()) # 组件分解
planning_graph.add_node("data_arch_design", DataArchDesignNode())        # 数据架构
planning_graph.add_node("api_planning", APIPlanningNode())              # API 规划
planning_graph.add_node("deployment_planning", DeploymentPlanningNode()) # 部署规划
planning_graph.add_node("plan_assembler", PlanAssemblerNode())          # 整合输出
planning_graph.add_node("plan_self_check", PlanSelfCheckNode())         # 自检

planning_graph.set_entry_point("knowledge_augment")
planning_graph.add_edge("knowledge_augment", "pattern_recommend")
planning_graph.add_edge("pattern_recommend", "pattern_confirm")
planning_graph.add_edge("pattern_confirm", "tech_stack_select")
planning_graph.add_edge("tech_stack_select", "component_decompose")
planning_graph.add_edge("component_decompose", "data_arch_design")
planning_graph.add_edge("data_arch_design", "api_planning")
planning_graph.add_edge("api_planning", "deployment_planning")
planning_graph.add_edge("deployment_planning", "plan_self_check")

# 自检不通过则回退到 mode_confirm 或 tech_stack_select
planning_graph.add_conditional_edges(
    "plan_self_check",
    self_check_and_route,
    {
        "pass": "plan_assembler",
        "fix_pattern": "pattern_confirm",
        "fix_tech_stack": "tech_stack_select",
        "fix_component": "component_decompose",
    }
)
planning_graph.add_edge("plan_assembler", END)
```

### 5.2 各节点设计

#### 5.2.1 KnowledgeAugmentNode

```python
class KnowledgeAugmentNode:
    """
    用 AnalysisResult 中的标签和实体从 Knowledge Layer 检索上下文
    为后续规划提供知识支撑
    """
    def run(self, state: PlanningState) -> PlanningState:
        analysis = state.analysis_result
        
        # 多角度检索
        queries = []
        
        # 1. 按领域标签检索
        for tag in analysis.domain_tags:
            queries.append(f"{tag} 技术架构方案")
        
        # 2. 按需求类别检索
        categories = set(r.category for r in analysis.requirements)
        for cat in categories:
            queries.append(f"{cat} 模块设计最佳实践")
        
        # 3. 按约束检索
        for cons in analysis.critical_constraints:
            queries.append(cons.description)
        
        # 4. 按实体检索
        for ent in analysis.entities[:5]:  # 取前5个
            queries.append(ent.name)
        
        # 执行检索
        results = []
        for q in queries[:10]:  # 最多 10 条检索
            ctx = knowledge_retrieval_tool.run(query=q, top_k=5)
            results.extend(ctx.docs)
        
        # 去重合并
        state.knowledge_context = self.merge_contexts(results)
        state.planning_notes.append(
            f"从知识图谱检索了 {len(queries)} 个角度，"
            f"获得 {len(state.knowledge_context.docs)} 条上下文"
        )
        return state
    
    def merge_contexts(self, all_docs: list[ScoredDoc]) -> RetrievalContext:
        """去重合并多个检索结果"""
        seen = set()
        unique = []
        for doc in all_docs:
            if doc.id not in seen:
                seen.add(doc.id)
                unique.append(doc)
        return RetrievalContext(docs=unique[:20])
```

#### 5.2.2 PatternRecommendNode

```python
class PatternRecommendNode:
    """
    根据需求特征推荐架构模式
    推荐多种方案 + 优劣势分析，支持多选
    """
    
    PATTERN_PROMPT = """
    你是一个资深软件架构师。根据以下需求分析结果和参考知识，
    推荐 2-3 个候选架构模式，并进行对比分析。
    
    ## 需求分析结果
    - 项目名称：{project_name}
    - 功能需求数量：{func_count}（其中 P0: {p0_count}）
    - 非功能需求重点：{nfr_focus}
    - 关键约束：{critical_constraints}
    - 业务领域：{domains}
    
    ## 知识库参考
    {knowledge_context}
    
    ## 请考虑以下架构模式（不限于此）：
    - 单体分层架构 (Monolithic Layered)
    - 微服务架构 (Microservices)
    - 事件驱动架构 (Event-Driven)
    - 六边形架构 (Hexagonal/Ports & Adapters)
    - CQRS
    - 整洁架构 (Clean Architecture)
    - Serverless 架构
    - 模块化单体 (Modular Monolith)
    
    对每个候选模式，请评估：
    1. 匹配度 (0-1)：与需求的匹配程度
    2. 优势：为什么适合这个项目
    3. 劣势：潜在问题
    4. 复杂度：实施难度 (低/中/高)
    5. 适用场景：什么条件下推荐此模式
    6. 历史案例：知识库中是否有类似案例
    
    输出 JSON 格式：
    [{{
        "pattern_name": "微服务架构",
        "match_score": 0.85,
        "strengths": ["...", "..."],
        "weaknesses": ["...", "..."],
        "complexity": "high",
        "recommendation": "适合团队规模大、需求独立迭代的场景",
        "similar_cases": ["电商平台v2", "支付中台"]
    }}]
    """
    
    def run(self, state: PlanningState) -> PlanningState:
        analysis = state.analysis_result
        
        # 汇总需求信息
        func_reqs = [r for r in analysis.requirements 
                     if r.type == "functional"]
        nfr_text = ", ".join([
            f"{r.category}({r.priority})" 
            for r in analysis.requirements if r.type == "non_functional"
        ])
        cons_text = "; ".join([
            c.description for c in analysis.critical_constraints
        ])
        ctx_text = self.format_context(state.knowledge_context)
        
        result = self.llm.complete(
            self.PATTERN_PROMPT.format(
                project_name=analysis.project_name,
                func_count=len(func_reqs),
                p0_count=len([r for r in func_reqs if r.priority == "P0"]),
                nfr_focus=nfr_text,
                critical_constraints=cons_text,
                domains=", ".join(analysis.domain_tags),
                knowledge_context=ctx_text,
            ),
            response_format={"type": "json_object"}
        )
        patterns = json.loads(result.text)
        state.architecture_patterns = [PatternEval(**p) for p in patterns]
        state.planning_notes.append(
            f"推荐了 {len(patterns)} 个候选架构模式："
            f"{', '.join(p['pattern_name'] for p in patterns)}"
        )
        return state
```

#### 5.2.3 TechStackSelectNode

```python
class TechStackSelectNode:
    """
    技术栈选型 - 按维度逐个决策，每个维度给出推荐 + 理由 + 替代方案
    """
    
    TECH_STACK_PROMPT = """
    你是一个资深技术选型专家。根据以下信息，为项目选择合适的技术栈。
    
    ## 架构模式
    {architecture_pattern}
    
    ## 关键需求
    {key_requirements}
    
    ## 关键约束
    {key_constraints}
    
    ## 知识库参考
    {knowledge_context}
    
    ## 需要决策的技术栈维度：
    {tech_dimensions}
    
    对每个维度，请考虑：
    1. 推荐技术及版本
    2. 核心理由（与需求/约束的对应关系）
    3. 替代方案
    4. 风险评估
    5. 团队要求（技能/学习成本）
    6. 知识库中相似项目的选型参考
    
    输出 JSON：
    [{{
        "dimension": "backend_framework",
        "recommendation": "Spring Boot 3.2 + JDK 17",
        "reason": "团队有 Java 背景，生态成熟，与微服务架构匹配",
        "alternatives": [{{"name": "Go Gin", "pros": [...], "cons": [...]}}],
        "risks": ["学习成本低"],
        "team_requirement": "3年以上Java经验",
        "knowledge_refs": ["历史方案-电商平台-技术选型"]
    }}]
    """
    
    TECH_DIMENSIONS = [
        "backend_framework",     # 后端框架
        "programming_language",  # 编程语言
        "database_primary",      # 主数据库
        "database_cache",        # 缓存
        "message_queue",         # 消息队列
        "api_gateway",           # API 网关
        "service_mesh",          # 服务网格（微服务需要）
        "frontend_framework",    # 前端框架（如需要）
        "ci_cd",                 # CI/CD
        "monitoring",            # 监控
        "containerization",      # 容器化
        "cloud_platform",        # 云平台
    ]
    
    def run(self, state: PlanningState) -> PlanningState:
        # 根据架构模式筛选需要的维度
        pattern = state.selected_pattern
        dimensions = self.filter_dimensions(pattern, self.TECH_DIMENSIONS)
        
        # 分批决策（LLM 一次处理太多维度会注意力分散）
        batch_size = 4
        all_choices = []
        
        for i in range(0, len(dimensions), batch_size):
            batch = dimensions[i:i+batch_size]
            result = self.llm.complete(
                self.TECH_STACK_PROMPT.format(
                    architecture_pattern=pattern.pattern_name,
                    key_requirements=self.summarize_reqs(state.analysis_result),
                    key_constraints=self.summarize_constraints(state.analysis_result),
                    knowledge_context=self.format_context(state.knowledge_context),
                    tech_dimensions="\n".join([f"- {d}" for d in batch]),
                ),
                response_format={"type": "json_object"}
            )
            choices = json.loads(result.text)
            all_choices.extend([TechChoice(**c) for c in choices])
        
        state.tech_stack_choices = all_choices
        return state
```

#### 5.2.4 ComponentDecomposeNode

```python
class ComponentDecomposeNode:
    """
    组件分解 - 将功能需求映射为系统组件
    输出：组件树 + 每个组件的职责、接口、依赖
    """
    
    DECOMPOSE_PROMPT = """
    你是一个系统架构师。根据以下信息进行组件分解。
    
    ## 架构模式
    {architecture_pattern}
    
    ## 技术栈
    {tech_stack}
    
    ## 功能需求
    {functional_requirements}
    
    ## 依赖关系
    {dependency_graph}
    
    ## 约束条件
    {constraints}
    
    请进行组件分解，输出结果包含：
    
    1. 组件列表 - 每个组件包含：
       - name: 组件名（如：用户服务、订单服务）
       - type: service(微服务) / module(模块) / library(库)
       - responsibility: 核心职责
       - key_functions: 负责的关键功能 [FR-xxx]
       - dependencies: 依赖的其他组件
       - api_count: 预计对外接口数量
       - suggested_team_size: 建议团队规模
    
    2. 组件间通信方式
       - 同步调用 (REST/gRPC)
       - 异步事件 (MQ)
       - 共享数据
    
    输出 JSON 格式。
    """
    
    def run(self, state: PlanningState) -> PlanningState:
        # 准备输入
        func_reqs = [r for r in state.analysis_result.requirements 
                     if r.type == "functional"]
        reqs_text = "\n".join([
            f"{r.id}[{r.priority}]: {r.description}"
            for r in func_reqs
        ])
        deps_text = json.dumps(
            state.analysis_result.dependency_graph.edges,
            ensure_ascii=False, indent=2
        )
        cons_text = "\n".join([
            f"[{c.severity}] {c.description}"
            for c in state.analysis_result.critical_constraints
        ])
        tech_text = "\n".join([
            f"{c.dimension}: {c.recommendation} ({c.reason[:50]})"
            for c in state.tech_stack_choices
        ])
        
        result = self.llm.complete(
            self.DECOMPOSE_PROMPT.format(
                architecture_pattern=state.selected_pattern.pattern_name,
                tech_stack=tech_text,
                functional_requirements=reqs_text,
                dependency_graph=deps_text,
                constraints=cons_text,
            ),
            response_format={"type": "json_object"}
        )
        data = json.loads(result.text)
        
        components = []
        for c in data.get("components", []):
            components.append(Component(**c))
        
        state.component_decomposition = components
        state.planning_notes.append(
            f"分解为 {len(components)} 个组件："
            f"{', '.join(c.name for c in components)}"
        )
        return state
```

#### 5.2.5 PlanSelfCheckNode

```python
class PlanSelfCheckNode:
    """
    规划自检 - 检查规划的一致性和完整性
    这是规划层的关键质量门禁
    """
    
    SELF_CHECK_PROMPT = """
    检查以下架构规划方案是否存在问题。
    
    ## 需求
    {requirements}
    
    ## 架构模式
    {pattern}
    
    ## 技术栈
    {tech_stack}
    
    ## 组件分解
    {components}
    
    ## 约束条件
    {constraints}
    
    请检查以下维度：
    1. completeness: 所有 P0/P1 需求是否都有组件覆盖？
    2. consistency: 技术栈之间是否兼容？组件依赖是否有循环？
    3. constraint_satisfaction: 所有 must 约束是否被满足？
    4. feasibility: 方案是否可行（团队/时间/预算）？
    5. conflict: 是否存在自相矛盾？
    
    输出 JSON：
    {{
        "passed": true/false,
        "issues": [
            {{
                "severity": "error" / "warning",
                "dimension": "completeness",
                "description": "需求 FR-005 '分布式事务' 没有组件对应",
                "suggestion": "考虑在订单服务中增加分布式事务模块"
            }}
        ],
        "suggested_action": "fix_pattern" / "fix_tech_stack" / "fix_component" / "pass"
    }}
    """
    
    def run(self, state: PlanningState) -> PlanningState:
        # 构建检查输入
        result = self.llm.complete(
            self.SELF_CHECK_PROMPT.format(
                requirements=self.summarize_reqs(state.analysis_result),
                pattern=state.selected_pattern.pattern_name,
                tech_stack=self.summarize_tech(state.tech_stack_choices),
                components=self.summarize_components(state.component_decomposition),
                constraints=self.summarize_constraints(state.analysis_result),
            ),
            response_format={"type": "json_object"}
        )
        check = json.loads(result.text)
        
        if check.get("passed", False):
            state.planning_notes.append("✅ 规划自检通过")
        else:
            issues = check.get("issues", [])
            errors = [i for i in issues if i.get("severity") == "error"]
            state.planning_notes.append(
                f"⚠️ 规划自检发现 {len(errors)} 个错误, "
                f"{len(issues) - len(errors)} 个警告"
            )
        
        return state
```

### 5.3 PlanningResult 输出模型

```python
class PlanningResult(BaseModel):
    """规划层最终输出"""
    
    # 架构模式
    architecture_pattern: ArchitecturePattern
    pattern_reasoning: str
    
    # 技术栈
    tech_stack: list[TechChoice]
    tech_stack_summary: str
    
    # 组件
    components: list[Component]
    component_diagram: str                    # Mermaid 组件图
    
    # 数据架构
    data_architecture: DataArchitecture
    
    # API
    api_design: APIDesign
    
    # 部署
    deployment: DeploymentPlan
    
    # 决策记录
    decisions: list[Decision]
    
    class TechChoice(BaseModel):
        dimension: str
        recommendation: str
        reason: str
        alternatives: list[AltChoice]
        risks: list[str]
        team_requirement: str
    
    class Component(BaseModel):
        name: str
        type: Literal["service", "module", "library"]
        responsibility: str
        key_functions: list[str]
        dependencies: list[str]
        api_count: int
        suggested_team_size: str
    
    class Decision(BaseModel):
        """记录每个关键决策点"""
        node: str                    # 哪个节点做出的决策
        topic: str                   # 决策主题
        choices: list[str]           # 考虑的选项
        selected: str               # 选择的选项
        reasoning: str              # 理由
        knowledge_refs: list[str]   # 参考的知识来源
```

### 5.4 Planning Layer 补充节点

#### 5.4.1 成本估算

```python
class CostEstimatorNode:
    """
    根据技术栈和规模估算：
    - 服务器/云成本
    - License费用
    - 人力成本
    - 运维成本
    """
    
    COST_PROMPT = """
    你是一个云成本架构师。根据以下技术方案估算月度运营成本。
    
    ## 技术栈方案
    {tech_stack}
    
    ## 组件列表
    {components}
    
    ## 数据架构
    {data_arch}
    
    ## 部署方案
    {deployment}
    
    ## 用户规模估算
    - DAU: {estimated_dau}
    - 数据量/月: {estimated_data_growth}
    
    请估算以下成本项：
    
    1. 计算资源（CPU/内存）
       - 每个组件的 Pod/VM 规格和数量
       - 月度费用
    
    2. 存储资源
       - 数据库实例规格
       - 对象存储用量
       - 备份存储
    
    3. 网络资源
       - 带宽费用
       - API调用费用
    
    4. 中间件服务
       - Redis/MQ 规格
       - 监控/日志服务
    
    5. License/订阅
       - 商业软件许可
       - 云服务订阅
    
    6. 人力成本（可选）
       - 按团队规模和当地薪资水平估算
    
    7. 3种配置方案
       - 低成本方案（创业期）
       - 标准方案（成长期）
       - 高可用方案（成熟期）
    
    输出 JSON：
    {{
        "low_cost": {{
            "monthly_total_usd": 1500,
            "breakdown": {{"compute": 800, "storage": 300, "network": 200, "middleware": 200}},
            "description": "适合MVP阶段，单机部署+少量预留"
        }},
        "standard": {{
            "monthly_total_usd": 4500,
            "breakdown": {{"compute": 2500, "storage": 800, "network": 400, "middleware": 500, "license": 300}},
            "description": "适合正式上线，集群部署+HA"
        }},
        "high_availability": {{
            "monthly_total_usd": 12000,
            "breakdown": {{"compute": 6000, "storage": 2000, "network": 1000, "middleware": 1500, "license": 1500}},
            "description": "适合大型生产环境，多地容灾+全链路冗余"
        }},
        "recommendation": "standard",
        "year_one_total_usd": 60000,
        "assumptions": ["基于阿里云/aws定价", "6人团队人力另计"]
    }}
    """
    
    def run(self, state: PlanningState) -> PlanningState:
        result = self.llm.complete(
            self.COST_PROMPT.format(
                tech_stack=self.summarize_tech(state.tech_stack_choices),
                components=self.summarize_components(state.component_decomposition),
                data_arch=state.data_architecture.summary(),
                deployment=state.deployment_plan.summary(),
                estimated_dau=self.estimate_dau(state.analysis_result),
                estimated_data_growth=self.estimate_data_growth(state.analysis_result),
            ),
            response_format={"type": "json_object"}
        )
        state.cost_estimation = json.loads(result.text)
        state.planning_notes.append(
            f"成本估算完成：标准方案月均 ${state.cost_estimation['standard']['monthly_total_usd']}"
        )
        return state
```

#### 5.4.2 时间线规划（甘特图生成）

```python
class TimelinePlannerNode:
    """
    根据组件依赖和团队规模生成实施时间线
    输出：Mermaid 甘特图 + 里程碑
    """
    
    TIMELINE_PROMPT = """
    你是一个项目管理专家。根据以下信息生成实施时间线。
    
    ## 组件列表（含依赖关系）
    {components_with_deps}
    
    ## 建议团队规模
    {team_size}
    
    ## 成本估算（用于排期参考）
    {cost_estimation}
    
    ## 约束条件
    {constraints}
    
    请生成：
    
    1. 阶段划分（建议2-4期）
    2. 每期包含的组件
    3. 每期工期（周）
    4. 里程碑节点
    5. 依赖关系（哪些组件必须等前面的完成）
    6. 关键路径
    7. 并行工作建议
    
    输出 JSON：
    {{
        "phases": [
            {{
                "name": "Phase 1: 基础平台",
                "duration_weeks": 6,
                "components": ["用户服务", "认证中心", "API网关"],
                "milestones": ["M1: 用户认证上线", "M2: 基础API就绪"],
                "team_allocation": {{"backend": 4, "frontend": 2, "devops": 1}},
                "dependencies": [],
                "risks": ["技术栈选型延迟"]
            }}
        ],
        "critical_path": ["用户服务", "订单服务", "支付服务"],
        "total_duration_weeks": 24,
        "recommended_team_size": 8,
        "parallel_suggestions": ["Phase 2的数据服务和报表服务可以并行开发"],
        "mermaid_gantt": "gantt\\n    title 实施计划\\n    dateFormat  YYYY-MM-DD\\n    section Phase 1\\n    用户服务 :2026-08-01, 30d\\n    ..."
    }}
    """
    
    def run(self, state: PlanningState) -> PlanningState:
        comps_with_deps = []
        for c in state.component_decomposition:
            comps_with_deps.append({
                "name": c.name,
                "type": c.type,
                "dependencies": c.dependencies,
                "key_functions": c.key_functions
            })
        
        result = self.llm.complete(
            self.TIMELINE_PROMPT.format(
                components_with_deps=json.dumps(comps_with_deps, ensure_ascii=False),
                team_size=self.suggest_team_size(state.component_decomposition),
                cost_estimation=json.dumps(
                    getattr(state, 'cost_estimation', {}), ensure_ascii=False),
                constraints=self.summarize_constraints(state.analysis_result),
            ),
            response_format={"type": "json_object"}
        )
        state.timeline_plan = json.loads(result.text)
        state.planning_notes.append(
            f"时间线规划完成：共{len(state.timeline_plan['phases'])}期，"
            f"总工期{state.timeline_plan['total_duration_weeks']}周"
        )
        return state
```

#### 5.4.3 技能缺口分析

```python
class SkillGapAnalyzerNode:
    """
    分析团队现有技能 vs 方案需要的技能
    识别培训或招聘需求
    """
    
    SKILL_GAP_PROMPT = """
    你是一个技术团队管理顾问。分析以下技术方案的技能需求。
    
    ## 技术栈方案
    {tech_stack}
    
    ## 建议团队规模
    {team_size}
    
    ## 假设团队背景
    - 主要语言：Java (3年经验)
    - 熟悉Spring Boot，但微服务经验有限
    - 有MySQL经验，无NoSQL经验
    - 有前端React基础
    - DevOps能力偏弱
    
    请分析：
    
    1. 必需技能列表（按组件分类）
    2. 技能缺口（当前团队不具备的）
    3. 学习成本（低/中/高）
    4. 学习路径建议
    5. 招聘建议（哪些技能必须招聘，哪些可以内部培养）
    6. 风险等级
    
    输出 JSON：
    {{
        "required_skills": [
            {{"skill": "Spring Boot 3.x", "level": "advanced", "component": "后端服务", "gap": "none"}},
            {{"skill": "Kubernetes", "level": "intermediate", "component": "基础设施", "gap": "high", 
              "learning_cost": "high", "suggestion": "招聘1名DevOps或外包"}},
            {{"skill": "Event Sourcing/CQRS", "level": "advanced", "component": "订单服务", "gap": "medium",
              "learning_cost": "medium", "suggestion": "安排2周培训+1个POC"}}
        ],
        "critical_gaps": ["Kubernetes", "消息队列Kafka"],
        "training_plan": [
            {{"topic": "K8s实战", "duration": "2周", "format": "外部培训", "target": ["后端工程师"]}}
        ],
        "hiring_recommendations": [
            {{"position": "DevOps工程师", "count": 1, "urgency": "high"}}
        ],
        "risk_level": "medium",
        "risk_reason": "DevOps和消息队列技能缺口可通过招聘解决，K8s学习曲线3个月"
    }}
    """
    
    def run(self, state: PlanningState) -> PlanningState:
        result = self.llm.complete(
            self.SKILL_GAP_PROMPT.format(
                tech_stack=self.summarize_tech(state.tech_stack_choices),
                team_size=self.suggest_team_size(state.component_decomposition),
            ),
            response_format={"type": "json_object"}
        )
        state.skill_gap_analysis = json.loads(result.text)
        state.planning_notes.append(
            f"技能缺口分析完成：关键缺口{len(state.skill_gap_analysis['critical_gaps'])}项"
        )
        return state
```

#### 5.4.4 风险量化

```python
class RiskQuantifierNode:
    """
    对每个技术选择给出风险概率+影响等级
    生成风险矩阵
    """
    
    RISK_PROMPT = """
    你是一个技术风险管理专家。分析以下技术方案的风险。
    
    ## 架构模式
    {pattern}
    
    ## 技术栈选项
    {tech_stack}
    
    ## 组件分解
    {components}
    
    ## 约束条件
    {constraints}
    
    对于每项风险，评估：
    - 风险描述
    - 类别（技术/团队/进度/成本/安全/外部）
    - 概率（0-1）
    - 影响（1-5）
    - 风险值 = 概率 × 影响
    - 应对策略（规避/减轻/转移/接受）
    - 应急预案
    - 触发条件
    
    输出 JSON：
    {{
        "risks": [
            {{
                "category": "技术",
                "description": "微服务拆分粒度过细导致运维复杂度倍增",
                "probability": 0.6,
                "impact": 4,
                "risk_score": 2.4,
                "level": "high",
                "mitigation": "采用模块化单体起步，按需逐步拆分",
                "contingency": "如果微服务超过20个，引入Service Mesh",
                "trigger": "组件数 > 15"
            }}
        ],
        "risk_matrix": {{
            "critical": ["微服务治理复杂度"],
            "high": ["K8s技能缺口", "分布式事务一致性"],
            "medium": ["第三方支付依赖", "数据迁移风险"],
            "low": ["前端框架版本升级"]
        }},
        "overall_risk_level": "medium",
        "top_3_risks": ["...", "...", "..."]
    }}
    """
    
    def run(self, state: PlanningState) -> PlanningState:
        result = self.llm.complete(
            self.RISK_PROMPT.format(
                pattern=state.selected_pattern.pattern_name,
                tech_stack=self.summarize_tech(state.tech_stack_choices),
                components=self.summarize_components(state.component_decomposition),
                constraints=self.summarize_constraints(state.analysis_result),
            ),
            response_format={"type": "json_object"}
        )
        state.risk_quantification = json.loads(result.text)
        return state
```

#### 5.4.5 PlanningState 补充 & Graph 扩展

```python
class PlanningState(TypedDict):
    # ... 原有字段 ...
    
    # --- 新增字段 ---
    cost_estimation: dict                    # 成本估算
    timeline_plan: dict                      # 时间线规划
    skill_gap_analysis: dict                 # 技能缺口
    risk_quantification: dict                # 风险量化

# 规划层 Graph 增加对应节点
planning_graph.add_node("cost_estimate", CostEstimatorNode())
planning_graph.add_node("timeline_planning", TimelinePlannerNode())
planning_graph.add_node("skill_gap_analysis", SkillGapAnalyzerNode())
planning_graph.add_node("risk_quantify", RiskQuantifierNode())

# 新流程：组件分解 → 成本估算 → 时间线 → 技能缺口 → 风险量化 → 数据架构
planning_graph.add_edge("component_decompose", "cost_estimate")
planning_graph.add_edge("cost_estimate", "timeline_planning")
planning_graph.add_edge("timeline_planning", "skill_gap_analysis")
planning_graph.add_edge("skill_gap_analysis", "risk_quantify")
planning_graph.add_edge("risk_quantify", "data_arch_design")

# 自检路由扩展：可回退到 cost_estimate 或 skill_gap_analysis
planning_graph.add_conditional_edges(
    "plan_self_check",
    self_check_and_route,
    {
        "pass": "plan_assembler",
        "fix_pattern": "pattern_confirm",
        "fix_tech_stack": "tech_stack_select",
        "fix_component": "component_decompose",
        "fix_cost": "cost_estimate",         # 新增
        "fix_plan": "timeline_planning",      # 新增
    }
)
```

---

## 六、Layer 4: Generation Layer — 方案生成 Agent

### 6.1 Agent Graph 结构

```python
class GenerationState(TypedDict):
    planning_result: PlanningResult
    analysis_result: AnalysisResult
    knowledge_context: RetrievalContext
    outline: list[SectionOutline]
    section_contents: dict[str, str]     # {section_id: content}
    code_scaffold: CodeScaffold
    consistency_report: ConsistencyReport
    formatted_docs: dict[str, str]       # {format: content}
    generation_result: GenerationResult

generation_graph = StateGraph(GenerationState)

generation_graph.add_node("outline_generator", OutlineGeneratorNode())
generation_graph.add_node("section_writer", SectionWriterNode())
generation_graph.add_node("diagram_generator", DiagramGeneratorNode())  # ⭐⭐ 新增: 架构图自动生成
generation_graph.add_node("code_scaffold_generator", CodeScaffoldGeneratorNode())
generation_graph.add_node("consistency_checker", ConsistencyCheckerNode())
generation_graph.add_node("revision_node", RevisionNode())           # 修复不通过的部分
generation_graph.add_node("format_assembler", FormatAssemblerNode()) # 格式组装

generation_graph.set_entry_point("outline_generator")
generation_graph.add_edge("outline_generator", "section_writer")

# SectionWriter 支持并行写多个章节 → ⭐⭐ 完成后走图表生成
generation_graph.add_conditional_edges(
    "section_writer",
    check_all_sections_done,
    {
        "continue_writing": "section_writer",   # 还有章节未写
        "all_done": "diagram_generator",         # ⭐⭐ 所有章节写完 → 先出图
    }
)

# ⭐⭐ 图表生成 → 代码骨架 → 一致性检查
generation_graph.add_edge("diagram_generator", "code_scaffold_generator")
generation_graph.add_edge("code_scaffold_generator", "consistency_checker")

# 一致性检查不通过 → 修复
generation_graph.add_conditional_edges(
    "consistency_checker",
    needs_revision,
    {
        "pass": "format_assembler",
        "fix_sections": "revision_node",
        "fix_all": "section_writer",             # 严重问题，整章重写
    }
)

generation_graph.add_edge("revision_node", "consistency_checker")  # 修复后再检查
generation_graph.add_edge("format_assembler", END)
```

### 6.2 OutlineGeneratorNode

```python
class OutlineGeneratorNode:
    """
    根据 PlanningResult 生成技术方案大纲
    """
    
    OUTLINE_PROMPT = """
    你是一个技术方案文档专家。根据以下架构规划结果，生成详细的技术方案文档大纲。
    
    ## 项目名称
    {project_name}
    
    ## 架构模式
    {pattern}
    
    ## 技术栈
    {tech_stack}
    
    ## 组件列表
    {components}
    
    ## 需求摘要
    {requirement_summary}
    
    请生成标准的技术方案文档大纲，包含以下标准章节，并可根据需要增删子节：
    
    1. 项目概述
       1.1 背景与目标
       1.2 范围与边界
       1.3 术语表
    2. 总体架构设计
       2.1 架构模式选择
       2.2 系统架构图
       2.3 技术栈全景
    3. 模块详细设计
       (每个组件一个子节)
       3.1 {component1}
          3.1.1 核心职责
          3.1.2 内部模块
          3.1.3 接口定义
          3.1.4 数据模型
          3.1.5 关键流程
       3.2 {component2} ...
    4. 数据架构设计
       4.1 数据模型总览
       4.2 数据库选型方案
       4.3 数据流设计
       4.4 数据治理
    5. API 设计
       5.1 API 风格
       5.2 核心接口列表
       5.3 接口安全设计
    6. 部署架构
       6.1 部署拓扑
       6.2 环境规划
       6.3 CI/CD 流程
    7. 安全设计
       7.1 认证授权
       7.2 数据安全
       7.3 安全合规
    8. 质量保障
       8.1 测试策略
       8.2 监控告警
       8.3 灾备方案
    9. 演进规划
       9.1 实施阶段
       9.2 风险与应对
    
    输出 JSON：
    [{{
        "section_id": "1",
        "title": "项目概述",
        "level": 1,
        "children": [
            {{"section_id": "1.1", "title": "背景与目标", "level": 2, 
              "description": "简述项目背景和核心目标", 
              "required_info": ["prd_background"],
              "estimated_tokens": 500}},
            ...
        ],
        "description": "概述项目整体情况",
        "estimated_tokens": 200,
        "source_refs": ["analysis.background"]
    }}]
    """
    
    def run(self, state: GenerationState) -> GenerationState:
        planning = state.planning_result
        analysis = state.analysis_result
        
        comp_names = [c.name for c in planning.components]
        
        result = self.llm.complete(
            self.OUTLINE_PROMPT.format(
                project_name=analysis.project_name,
                pattern=planning.architecture_pattern.pattern_name,
                tech_stack=self.summarize_tech(planning.tech_stack),
                components="\n".join([f"       {c.name} - {c.responsibility}" 
                                      for c in planning.components]),
                requirement_summary=self.summarize_reqs(analysis),
            ),
            response_format={"type": "json_object"}
        )
        sections = json.loads(result.text)
        state.outline = [SectionOutline(**s) for s in sections]
        state.planning_notes.append(
            f"生成技术方案大纲：{len(sections)} 个一级章节"
        )
        return state
```

### 6.3 SectionWriterNode

```python
class SectionWriterNode:
    """
    逐节生成 - 支持并行执行
    每节生成时自动注入相关知识
    """
    
    SECTION_PROMPT = """
    你是一个技术方案文档撰写专家。请根据大纲、架构规划和参考知识，撰写指定章节。
    
    ## 章节信息
    章节ID: {section_id}
    章节标题: {title}
    章节描述: {description}
    
    ## 所需信息
    {required_info_context}
    
    ## 架构规划参考
    架构模式：{pattern}
    技术栈：{tech_stack}
    组件设计：{components}
    数据架构：{data_arch}
    部署方案：{deployment}
    
    ## 知识库参考（相关上下文）
    {knowledge_context}
    
    ## 写作要求
    1. 内容必须基于输入的架构规划，不要凭空发挥
    2. 提及具体技术时给出理由
    3. 涉及决策时引用决策理由
    4. 使用专业的技术文档风格
    5. 预估字数：{estimated_tokens} tokens
    
    请输出该章节的完整内容（Markdown 格式）。
    """
    
    def run(self, state: GenerationState) -> GenerationState:
        # 确定当前需要写的章节
        pending = [s for s in state.outline 
                   if s.section_id not in state.section_contents]
        
        if not pending:
            return state  # 全部写完
        
        # 每次写 1-2 节（避免一次太长）
        batch = pending[:2]
        
        for section in batch:
            context = self.prepare_section_context(section, state)
            
            result = self.llm.complete(
                self.SECTION_PROMPT.format(
                    section_id=section.section_id,
                    title=section.title,
                    description=section.description,
                    required_info_context=context,
                    pattern=state.planning_result.architecture_pattern.pattern_name,
                    tech_stack=self.summarize_tech(state.planning_result.tech_stack),
                    components=self.summarize_components(state.planning_result.components),
                    data_arch=state.planning_result.data_architecture.summary(),
                    deployment=state.planning_result.deployment.summary(),
                    knowledge_context=self.format_context(state.knowledge_context),
                    estimated_tokens=section.estimated_tokens,
                )
            )
            state.section_contents[section.section_id] = result.text
        
        return state
    
    def prepare_section_context(self, section: SectionOutline, 
                               state: GenerationState) -> str:
        """为特定章节准备上下文"""
        contexts = []
        for ref in section.source_refs:
            if ref.startswith("analysis."):
                field = ref.split(".")[1]
                contexts.append(getattr(state.analysis_result, field, ""))
            elif ref.startswith("planning."):
                field = ref.split(".")[1]
                contexts.append(getattr(state.planning_result, field, ""))
        return "\n".join(str(c) for c in contexts if c)
```

### 6.4 ConsistencyCheckerNode

```python
class ConsistencyCheckerNode:
    """
    一致性检查：
    - 方案内容是否与 PRD 需求一致
    - 方案内部是否一致（前面的章节和后面的不矛盾）
    - 技术栈选择是否与约束一致
    - 数据流是否完整
    """
    
    CONSISTENCY_PROMPT = """
    你是一个技术方案质量审核专家。
    检查生成的技术方案文档是否存在一致性问题。
    
    ## 原始 PRD 需求
    {prd_requirements}
    
    ## 方案文档内容
    {document_content}
    
    ## 请逐项检查：
    1. PRD覆盖度：所有 P0 需求是否在方案中有对应设计？
    2. 内部一致性：方案不同章节之间是否有矛盾？
       - 架构描述 vs 组件职责
       - API 设计 vs 数据模型
       - 部署方案 vs 性能约束
    3. 技术一致性：选型是否自洽？
       - 语言版本与框架版本兼容
       - 组件间通信协议一致
    4. 约束满足：所有 must 约束是否被满足？
    
    输出 JSON：
    {{
        "passed": true/false,
        "coverage": {{
            "p0_covered": ["FR-001", "FR-002"],
            "p0_missing": ["FR-003"],
            "coverage_rate": 0.85
        }},
        "conflicts": [
            {{
                "severity": "error",
                "description": "第3章说用MySQL，第4章数据流图显示用了MongoDB",
                "location_a": "3.2 数据库选型",
                "location_b": "4.3 数据流图",
                "suggestion": "统一为MySQL或补充多数据库的说明"
            }}
        ],
        "constraint_satisfaction": {{
            "satisfied": ["C001", "C002"],
            "violated": [],
            "unaddressed": ["C003"]
        }},
        "suggested_action": "pass" / "fix_sections" / "rewrite"
    }}
    """
    
    def run(self, state: GenerationState) -> GenerationState:
        doc_content = "\n\n".join([
            f"## {sid}\n{content}"
            for sid, content in state.section_contents.items()
        ])
        
        result = self.llm.complete(
            self.CONSISTENCY_PROMPT.format(
                prd_requirements=self.summarize_reqs(state.analysis_result),
                document_content=doc_content[:12000],  # 限制长度
            ),
            response_format={"type": "json_object"}
        )
        report = json.loads(result.text)
        state.consistency_report = ConsistencyReport(**report)
        return state
```

### 6.5 CodeScaffoldGeneratorNode

```python
class CodeScaffoldGeneratorNode:
    """
    根据组件分解和架构设计生成项目代码框架
    - 项目结构
    - 核心接口定义
    - 数据模型定义
    - 配置文件
    """
    
    SCAFFOLD_PROMPT = """
    你是一个代码架构师。根据以下架构设计，生成项目的代码框架。
    
    ## 技术栈
    {tech_stack}
    
    ## 组件列表
    {components}
    
    ## 数据模型
    {data_architecture}
    
    ## API 设计
    {api_design}
    
    请生成：
    1. 项目目录结构（按组件拆分）
    2. 核心接口定义（interface / abstract class）
    3. 数据模型定义（entity / model class）
    4. 配置文件（application.yml / config）
    5. 依赖管理文件（pom.xml / build.gradle / requirements.txt）
    6. Dockerfile 和 docker-compose（按组件）
    
    输出 JSON：
    {{
        "language": "java",
        "project_structure": {{
            "root": "project-name/",
            "directories": [
                "project-name/src/main/java/com/company/...",
                ...
            ]
        }},
        "files": [
            {{
                "path": "src/main/java/com/company/UserService.java",
                "content": "...",
                "type": "interface"
            }}
        ],
        "build_files": {{
            "pom.xml": "..."
        }},
        "docker": {{
            "dockerfile": "...",
            "docker_compose": "..."
        }}
    }}
    """
    
    def run(self, state: GenerationState) -> GenerationState:
        result = self.llm.complete(
            self.SCAFFOLD_PROMPT.format(
                tech_stack=self.summarize_tech(state.planning_result.tech_stack),
                components=self.summarize_components(state.planning_result.components),
                data_architecture=state.planning_result.data_architecture.summary(),
                api_design=state.planning_result.api_design.summary(),
            ),
            response_format={"type": "json_object"}
        )
        data = json.loads(result.text)
        state.code_scaffold = CodeScaffold(**data)
        return state
```

### 6.6 DiagramGeneratorNode — ⭐⭐ 架构图自动生成节点

```python
class DiagramGeneratorNode:
    """
    架构图自动生成节点
    根据 PlanningResult 中的组件、关系、数据流、部署方案
    自动生成架构图 / 流程图 / 部署拓扑图 / ER 图
    
    输出:
    - Mermaid 代码（嵌入Markdown方案）
    - PNG/SVG 图片（PDF/DOCX/HTML导出用）
    """
    
    DIAGRAM_TYPES = {
        "architecture": {
            "prompt": "生成系统架构图，展示组件间关系",
            "template_key": "components_and_relations",
        },
        "data_flow": {
            "prompt": "生成数据流图，展示核心业务流程",
            "template_key": "data_flows",
        },
        "deployment": {
            "prompt": "生成部署拓扑图，展示服务部署结构",
            "template_key": "deployment_info",
        },
        "er_diagram": {
            "prompt": "生成ER图，展示核心数据模型",
            "template_key": "data_models",
        },
    }
    
    def run(self, state: GenerationState) -> GenerationState:
        planning = state.planning_result
        
        # 1. 架构图
        arch_diagram = self._generate_architecture_diagram(planning)
        state.generated_diagrams["architecture"] = arch_diagram
        
        # 2. 数据流图
        flow_diagram = self._generate_flow_diagram(planning)
        state.generated_diagrams["data_flow"] = flow_diagram
        
        # 3. 部署拓扑图
        deploy_diagram = self._generate_deployment_diagram(planning)
        state.generated_diagrams["deployment"] = deploy_diagram
        
        # 4. ER图（如果有数据模型）
        if planning.data_architecture and planning.data_architecture.models:
            er_diagram = self._generate_er_diagram(planning)
            state.generated_diagrams["er_diagram"] = er_diagram
        
        # 5. 将图表 Mermaid 代码注入对应章节
        self._inject_diagrams_to_sections(state)
        
        state.planning_notes.append(
            f"自动生成了 {len(state.generated_diagrams)} 张架构图: "
            f"{', '.join(state.generated_diagrams.keys())}"
        )
        return state
    
    def _generate_architecture_diagram(self, planning) -> GeneratedDiagram:
        """生成架构图"""
        generator = DiagramGenerator()
        return generator.generate_architecture_diagram(
            components=planning.components,
            relations=self._extract_relations(planning),
        )
    
    def _generate_flow_diagram(self, planning) -> GeneratedDiagram:
        """生成数据流图"""
        generator = DiagramGenerator()
        flows = self._extract_data_flows(planning)
        return generator.generate_flow_diagram(
            flows=flows,
            components=planning.components,
        )
    
    def _generate_deployment_diagram(self, planning) -> GeneratedDiagram:
        """生成部署拓扑图"""
        generator = DiagramGenerator()
        return generator.generate_deployment_diagram(planning.deployment)
    
    def _generate_er_diagram(self, planning) -> GeneratedDiagram:
        """生成 ER 图"""
        models = planning.data_architecture.models
        mermaid_code = "erDiagram\n"
        for model in models:
            mermaid_code += f"    {model.name} {{\n"
            for field in model.fields:
                mermaid_code += f"        {field.type} {field.name}\n"
            mermaid_code += "    }\n"
        for rel in planning.data_architecture.relationships:
            mermaid_code += (
                f"    {rel.source} {rel.cardinality} {rel.target} : {rel.label}\n"
            )
        
        png_bytes = self._render_to_png(mermaid_code)
        return GeneratedDiagram(
            diagram_type="er_diagram",
            mermaid_code=mermaid_code,
            png_base64=base64.b64encode(png_bytes).decode(),
        )
    
    def _inject_diagrams_to_sections(self, state: GenerationState):
        """将生成的图表 Mermaid 代码注入对应章节"""
        section_map = {
            "architecture": "2.2",    # 注入到"系统架构图"章节
            "data_flow": "4.3",       # 注入到"数据流设计"章节
            "deployment": "6.1",      # 注入到"部署拓扑"章节
            "er_diagram": "4.1",      # 注入到"数据模型总览"章节
        }
        for diagram_type, section_id in section_map.items():
            diagram = state.generated_diagrams.get(diagram_type)
            if diagram and section_id in state.section_contents:
                # 在章节末尾追加 Mermaid 代码块
                state.section_contents[section_id] += (
                    f"\n\n```mermaid\n{diagram.mermaid_code}\n```\n"
                )
    
    def _render_to_png(self, mermaid_code: str) -> bytes:
        """Mermaid → PNG 渲染"""
        try:
            result = subprocess.run(
                ["mmdc", "-i", "-", "-o", "-", "-f", "png"],
                input=mermaid_code.encode(),
                capture_output=True, timeout=30,
            )
            return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # 回退: Kroki API
            response = requests.post(
                f"{settings.KROKI_URL}/mermaid/png",
                json={"diagram": mermaid_code},
                timeout=15,
            )
            return response.content
```

### GenerationState 多模态扩展

```python
class GenerationState(TypedDict):
    # ... 原有字段 ...
    
    # --- ⭐⭐ 新增多模态字段 ---
    generated_diagrams: dict[str, GeneratedDiagram]  # {类型: 图表对象}
    multimodal_retrieval_results: list[ScoredImageChunk]  # 多模态检索结果
    
class GeneratedDiagram(BaseModel):
    """生成的图表"""
    diagram_type: str                               # architecture / data_flow / deployment / er_diagram
    mermaid_code: str                               # Mermaid 源码（嵌入Markdown）
    plantuml_code: Optional[str]                    # PlantUML 备选
    png_base64: Optional[str]                       # PNG base64（PDF/DOCX导出用）
    svg_content: Optional[str]                      # SVG 内容（HTML导出用）
    description: str = ""                           # 图表文字说明
```

### 6.7 模板系统（Template Engine）

```python
class TemplateEngine:
    """
    模板系统 - 行业/企业/章节三级模板
    """
    
    def __init__(self):
        self.templates = self.load_templates()
    
    def load_templates(self) -> dict:
        """加载模板配置"""
        return {
            "industry": {
                "ecommerce":    Template("templates/industry/ecommerce.yaml"),
                "fintech":      Template("templates/industry/fintech.yaml"),
                "healthcare":   Template("templates/industry/healthcare.yaml"),
                "iot":          Template("templates/industry/iot.yaml"),
                "saas":         Template("templates/industry/saas.yaml"),
            },
            "enterprise": {
                "default": Template("templates/enterprise/default.yaml"),
                # 企业客户可通过API上传自定义模板
            },
            "section": {
                "background":    Template("templates/section/background.md"),
                "architecture":  Template("templates/section/architecture.md"),
                "api_design":    Template("templates/section/api_design.md"),
                "security":      Template("templates/section/security.md"),
                "deployment":    Template("templates/section/deployment.md"),
            }
        }
    
    def select_template(self, analysis: AnalysisResult, 
                        enterprise_id: str = None) -> Template:
        """选择最适合的模板"""
        # 1. 优先使用企业模板
        if enterprise_id and enterprise_id in self.templates["enterprise"]:
            return self.templates["enterprise"][enterprise_id]
        
        # 2. 按行业匹配
        for tag in analysis.domain_tags:
            if tag in self.templates["industry"]:
                return self.templates["industry"][tag]
        
        # 3. 默认模板
        return self.templates["enterprise"]["default"]
    
    def render_section(self, section_type: str, 
                       context: dict, template: Template) -> str:
        """用模板渲染某个章节"""
        section_tpl = self.templates["section"].get(section_type)
        if not section_tpl:
            return ""  # 无模板则返回空，由SectionWriter决定
        
        # Jinja2 模板渲染
        jinja_tpl = Environment().from_string(section_tpl.content)
        return jinja_tpl.render(**context)
```

### 6.7 模板配置示例

```yaml
# templates/industry/ecommerce.yaml
name: "电商行业技术方案模板"
version: "1.0"
description: "适用于电商/零售行业的技术方案文档"

sections:
  - id: "project_overview"
    required: true
    content_template: |
      # 项目概述
      ## 1.1 背景与目标
      {prd_background}
      
      ## 1.2 业务范围
      - 覆盖渠道：{{ channels | default('Web, Mobile, MiniProgram') }}
      - 目标用户：{{ target_users | default('C端消费者') }}
      - 业务模式：{{ business_model | default('B2C') }}
      
      ## 1.3 关键业务指标
      - GMV目标：{{ gmv_target | default('待确认') }}
      - 订单峰值：{{ peak_orders | default('1000 TPS') }}
      - 转化率目标：{{ conversion_rate | default('3%') }}
  
  - id: "architecture_design"
    required: true
    sections:
      - "总体架构"
      - "交易链路设计"  # 电商特有
      - "库存设计"      # 电商特有
      - "物流设计"      # 电商特有
      - "营销设计"      # 电商特有
      - "商品设计"      # 电商特有
  
  - id: "inventory_design"
    required: false
    condition: "has_inventory_system"
    content_template: |
      # 库存设计
      ## 库存模型
      - 物理库存：实际仓库库存
      - 可售库存：物理库存 - 锁定库存
      - 锁定库存：下单未支付占用的库存
      
      ## 库存扣减策略
      - 下单预占：{{ inventory_lock_strategy | default('下单即锁定') }}
      - 超时释放：{{ release_after_minutes | default('30分钟') }}
      - 库存一致性：{{ consistency_guarantee | default('最终一致性') }}

variables:
  # 可在PRD中提取或用户手动填写的变量
  channels:
    description: "覆盖渠道"
    default: "Web, Mobile, MiniProgram"
  peak_orders:
    description: "订单峰值TPS"
    default: "1000"
```

### 6.9 多格式导出（⭐ 多模态增强版）

```python
class FormatExporter:
    """
    多格式输出引擎（⭐ 多模态增强版）
    支持：Markdown / PDF / DOCX / HTML / Confluence / Notion
    新增：自动将生成的 Mermaid 图表渲染为 PNG/SVG 嵌入输出文档
    """
    
    def export(self, doc_content: str, format: str, 
               metadata: DocMetadata,
               diagrams: dict[str, GeneratedDiagram] = None) -> ExportResult:
        """
        导出文档（可选携带图表）
        
        Args:
            doc_content: Markdown 格式文档内容
            format: 导出格式
            metadata: 文档元数据
            diagrams: ⭐ 生成的图表 {类型: GeneratedDiagram}
        """
        # ⭐ 将图表 PNG base64 注入文档内容
        if diagrams:
            doc_content = self._embed_diagrams(doc_content, diagrams)
        
        exporters = {
        exporters = {
            "markdown":    self.export_markdown,
            "pdf":         self.export_pdf,
            "docx":        self.export_docx,
            "html":        self.export_html,
            "confluence":  self.export_confluence,
            "notion":      self.export_notion,
        }
        exporter = exporters.get(format)
        if not exporter:
            raise ValueError(f"不支持的导出格式: {format}")
        return exporter(doc_content, metadata)
    
    def export_pdf(self, content: str, metadata: DocMetadata) -> ExportResult:
        """Markdown → PDF（通过 WeasyPrint / Pandoc）"""
        html = markdown_to_html(content, metadata)
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        
        return ExportResult(
            format="pdf",
            data=pdf_bytes,
            filename=f"{metadata.project_name}_技术方案.pdf",
            mime_type="application/pdf",
        )
    
    def export_docx(self, content: str, metadata: DocMetadata) -> ExportResult:
        """Markdown → DOCX（通过 python-docx-template）"""
        from docx import Document
        from htmldocx import HtmlToDocx
        
        html = markdown_to_html(content, metadata)
        doc = Document()
        
        # 设置企业模板样式
        if metadata.template_path:
            doc = Document(metadata.template_path)
        
        parser = HtmlToDocx()
        parser.add_html_to_document(html, doc)
        
        # 添加封面
        self._add_cover_page(doc, metadata)
        
        # 添加目录
        self._add_toc(doc)
        
        output = BytesIO()
        doc.save(output)
        
        return ExportResult(
            format="docx",
            data=output.getvalue(),
            filename=f"{metadata.project_name}_技术方案.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    
    def export_confluence(self, content: str, metadata: DocMetadata) -> ExportResult:
        """通过 Confluence API 直接发布"""
        confluence = ConfluenceAPI(
            url=settings.CONFLUENCE_URL,
            token=settings.CONFLUENCE_TOKEN,
        )
        
        page = confluence.create_page(
            space=metadata.confluence_space or "TECH",
            title=f"{metadata.project_name} - 技术方案",
            body=self.markdown_to_confluence(content),
            parent_id=metadata.confluence_parent_id,
        )
        
        return ExportResult(
            format="confluence",
            data={"page_id": page["id"], "url": page["_links"]["webui"]},
            filename=None,
            mime_type="application/json",
        )
    
    def export_notion(self, content: str, metadata: DocMetadata) -> ExportResult:
        """通过 Notion API 直接发布"""
        notion = NotionAPI(token=settings.NOTION_TOKEN)
        
        page = notion.pages.create(
            parent={"database_id": metadata.notion_database_id},
            properties={
                "title": {"title": [{"text": {"content": f"{metadata.project_name} - 技术方案"}}]},
                "状态": {"select": {"name": "待评审"}},
                "日期": {"date": {"start": datetime.today().isoformat()}},
            },
            children=self.markdown_to_notion_blocks(content),
        )
        
        return ExportResult(
            format="notion",
            data={"page_id": page["id"], "url": page["url"]},
            filename=None,
            mime_type="application/json",
        )
    
    def _embed_diagrams(self, content: str, 
                         diagrams: dict[str, GeneratedDiagram]) -> str:
        """⭐ 将 Mermaid 图表渲染为 PNG base64，替换 Markdown 中的 mermaid 代码块"""
        
        for diagram_type, diagram in diagrams.items():
            if not diagram.png_base64:
                continue
            
            # 查找 ```mermaid 代码块并替换为图片
            pattern = rf"```mermaid\n{re.escape(diagram.mermaid_code[:50])}.*?```"
            img_tag = (
                f"![{diagram_type}]"
                f"(data:image/png;base64,{diagram.png_base64})"
                f"\n*{diagram.description or diagram_type}*\n"
            )
            content = re.sub(pattern, img_tag, content, flags=re.DOTALL)
        
        return content
    
    def markdown_to_html(self, content: str, metadata: DocMetadata) -> str:
        """Markdown → HTML（含样式）"""
        html_content = markdown.markdown(
            content,
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{metadata.project_name} - 技术方案</title>
    <style>
        body {{ font-family: 'Noto Sans SC', sans-serif; max-width: 1200px; margin: 0 auto; padding: 40px; }}
        h1 {{ color: #1a1a2e; border-bottom: 2px solid #16213e; padding-bottom: 10px; }}
        h2 {{ color: #16213e; border-bottom: 1px solid #e0e0e0; padding-bottom: 5px; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #16213e; color: white; }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""
```

---

### 6.10 GenerationState 多模态补充 & Graph 扩展

```python
class GenerationState(TypedDict):
    # ... 原有字段 ...
    
    # --- 新增字段 ---
    template: Optional[Template]              # 选用的模板
    export_formats: list[str]                 # 需要导出的格式
    exported_files: dict[str, ExportResult]   # 导出结果
    
    # --- ⭐⭐ 多模态字段 ---
    generated_diagrams: dict[str, GeneratedDiagram]  # {类型: 图表对象}
    multimodal_retrieval_results: list[ScoredImageChunk]  # 多模态检索结果

# 生成层 Graph 增加节点
generation_graph.add_node("diagram_generator", DiagramGeneratorNode())  # 图表生成
generation_graph.add_node("format_exporter", FormatExporterNode())      # 导出

# 在 section_writer 之后增加图表生成
generation_graph.add_edge("diagram_generator", "code_scaffold_generator")

# 在 format_assembler 之后增加导出（携带 diagrams 参数）
generation_graph.add_edge("format_assembler", "format_exporter")
generation_graph.add_edge("format_exporter", END)
```

---

## 七、Evaluation System — 评测体系（完整版）

### 7.1 评测 Agent Graph

```python
eval_graph = StateGraph(EvaluationState)

eval_graph.add_node("prd_coverage_check", PRDCoverageCheckNode())       # PRD覆盖率
eval_graph.add_node("consistency_check", ConsistencyEvalNode())         # 一致性
eval_graph.add_node("feasibility_assessment", FeasibilityEvalNode())    # 可行性
eval_graph.add_node("architecture_quality", ArchitectureQualityNode())  # 架构质量
eval_graph.add_node("security_compliance", SecurityComplianceNode())    # 安全合规
eval_graph.add_node("scoring", ScoringNode())                           # 综合评分

eval_graph.set_entry_point("prd_coverage_check")

# 维度可以并行
eval_graph.add_edge("prd_coverage_check", "consistency_check")
eval_graph.add_edge("consistency_check", "feasibility_assessment")
eval_graph.add_edge("feasibility_assessment", "architecture_quality")
eval_graph.add_edge("architecture_quality", "security_compliance")
eval_graph.add_edge("security_compliance", "scoring")
eval_graph.add_edge("scoring", END)
```

### 7.2 各评估维度详细设计

#### 7.2.1 PRD Coverage Check

```python
class PRDCoverageCheckNode:
    """
    PRD 功能覆盖率检查
    逐条比对 PRD 需求是否在技术方案中有对应设计
    """
    
    COVERAGE_PROMPT = """
    检查技术方案是否覆盖了 PRD 中的每一条需求。
    
    ## PRD 需求列表
    {requirements}
    
    ## 技术方案内容
    {document_content}
    
    对每条需求，判断：
    - covered: 方案有明确设计对应此需求
    - partially_covered: 方案提到了但不够详细
    - not_covered: 方案完全没覆盖
    
    输出 JSON：
    {{
        "overall_coverage_rate": 0.85,
        "p0_coverage": 1.0,
        "p1_coverage": 0.8,
        "details": [
            {{
                "req_id": "FR-001",
                "priority": "P0",
                "description": "用户登录",
                "status": "covered",
                "evidence": "第3.1.2节 用户认证模块 设计了JWT登录流程",
                "suggestion": null
            }},
            {{
                "req_id": "FR-005",
                "priority": "P1",
                "description": "数据导出",
                "status": "not_covered",
                "evidence": null,
                "suggestion": "建议在报表服务中增加导出模块"
            }}
        ]
    }}
    """
    
    def run(self, state: EvaluationState) -> EvaluationState:
        result = self.llm.complete(
            self.COVERAGE_PROMPT.format(
                requirements="\n".join([
                    f"{r.id}[{r.priority}]: {r.description}"
                    for r in state.analysis_result.requirements
                ]),
                document_content=state.document_content[:15000],
            ),
            response_format={"type": "json_object"}
        )
        state.coverage_report = json.loads(result.text)
        return state
```

#### 7.2.2 Feasibility Assessment

```python
class FeasibilityEvalNode:
    """
    技术可行性评估
    从 Knowledge Layer 检索类似方案，评估当前方案的可行性
    """
    
    FEASIBILITY_PROMPT = """
    作为一个资深技术架构师，评估以下技术方案的可行性。
    
    ## 技术方案摘要
    - 架构模式：{pattern}
    - 技术栈：{tech_stack}
    - 组件数量：{component_count}
    - 关键约束：{constraints}
    
    ## 类似历史方案参考
    {historical_cases}
    
    ## 评估维度（每项 1-5 分）：
    1. 技术成熟度：所选技术是否经过大规模验证？
    2. 团队可实施性：在常见团队规模和能力下是否可行？
    3. 时间合理性：方案复杂度与预期时间是否匹配？
    4. 成本效益：技术选择是否经济合理？
    5. 风险等级：主要风险是否可控？
    
    输出 JSON：
    {{
        "feasibility_score": 4.2,
        "maturity": {{"score": 5, "reason": "Spring Boot + PostgreSQL 是成熟组合"}},
        "implementability": {{"score": 4, "reason": "...", "risks": ["需要引入消息队列中间件专家"]}},
        "timeline": {{"score": 3, "reason": "16个组件对6人团队偏多", "suggestion": "建议分阶段交付"}},
        "cost": {{"score": 4, "reason": "...", "estimated_monthly": "$2000-3000"}},
        "risk_level": "medium",
        "overall_assessment": "方案整体可行，但建议分两期实施",
        "knowledge_refs": ["类似项目X的可行性分析"]
    }}
    """
    
    def run(self, state: EvaluationState) -> EvaluationState:
        # 从知识图谱检索类似案例
        similar_queries = [
            f"{state.planning_result.architecture_pattern} 实施案例",
            f"{state.planning_result.tech_stack[0].recommendation} 生产案例",
        ]
        historical = ""
        for q in similar_queries:
            ctx = knowledge_retrieval_tool.run(query=q, top_k=3)
            historical += self.format_context(ctx) + "\n"
        
        result = self.llm.complete(
            self.FEASIBILITY_PROMPT.format(
                pattern=state.planning_result.architecture_pattern,
                tech_stack=self.summarize_tech(state.planning_result.tech_stack),
                component_count=len(state.planning_result.components),
                constraints=self.summarize_constraints(state.analysis_result),
                historical_cases=historical,
            ),
            response_format={"type": "json_object"}
        )
        state.feasibility_report = json.loads(result.text)
        return state
```

#### 7.2.3 Architecture Quality Assessment

```python
class ArchitectureQualityNode:
    """
    架构质量评估 - 基于架构设计原则
    """
    
    QUALITY_PROMPT = """
    作为软件架构评估专家，基于以下原则评估架构质量：
    
    ## 架构设计
    {architecture_detail}
    
    ## 评估维度：
    1. SOLID 原则遵循度
       - 单一职责：组件职责是否聚焦？
       - 开闭原则：是否易于扩展？
       - 依赖倒置：高层是否依赖抽象？
    
    2. 非功能属性 (ISO 25010)
       - 可维护性：模块化程度
       - 可测试性：组件是否可独立测试
       - 可扩展性：添加新功能的工作量
       - 性能：预估性能瓶颈
       - 可用性：单点故障分析
    
    3. 架构风格匹配度
       - 所选模式与需求的匹配度
    
    输出 JSON：
    {{
        "overall_quality": 4.0,
        "solid": {{
            "srp": {{"score": 4, "issues": ["订单服务职责偏多"], "suggestion": "拆分订单写入和查询"}},
            "ocp": {{"score": 4, "issues": [], "suggestion": null}},
            "dip": {{"score": 5, "issues": [], "suggestion": null}}
        }},
        "non_functional": {{
            "maintainability": 4,
            "testability": 4,
            "extensibility": 3,
            "performance": 4,
            "availability": 3
        }},
        "pattern_match": 4,
        "bottlenecks": ["订单服务可能成为性能瓶颈", "单数据库实例的可用性风险"],
        "recommendations": ["考虑订单服务读写分离", "数据库主从+自动故障转移"]
    }}
    """
    
    def run(self, state: EvaluationState) -> EvaluationState:
        planning = state.planning_result
        arch_detail = f"""
架构模式: {planning.architecture_pattern}
组件分解: {chr(10).join([f'- {c.name}({c.type}): {c.responsibility}' for c in planning.components])}
数据架构: {planning.data_architecture.summary()}
部署方案: {planning.deployment.summary()}
"""
        result = self.llm.complete(
            self.QUALITY_PROMPT.format(architecture_detail=arch_detail),
            response_format={"type": "json_object"}
        )
        state.quality_report = json.loads(result.text)
        return state
```

#### 7.2.4 Security Compliance Check

```python
class SecurityComplianceNode:
    """
    安全合规检查
    """
    
    SECURITY_PROMPT = """
    对以下技术方案进行安全合规审查。
    
    ## 技术方案摘要
    {planning_summary}
    
    ## 检查清单
    1. 认证机制：是否使用了标准的认证协议？
    2. 授权模型：是否有完善的权限体系？
    3. 数据加密：敏感数据是否加密存储和传输？
    4. 通信安全：内部服务通信是否加密？
    5. 日志审计：是否有完整的操作日志？
    6. 输入验证：是否防范注入攻击？
    7. 依赖安全：所选组件是否有已知漏洞？
    8. 合规要求：是否满足{regulations}要求？
    
    输出 JSON：
    {{
        "overall_compliance": 3.5,
        "critical_issues": [
            {{
                "severity": "high",
                "item": "认证机制",
                "description": "方案未明确说明使用OAuth2还是JWT",
                "regulation": "OWASP ASVS V2",
                "suggestion": "明确使用OAuth2.0 + JWT，并说明Token刷新策略"
            }}
        ],
        "warnings": [...],
        "passed_checks": ["数据加密", "输入验证"],
        "suggested_actions": ["补充认证授权章节", "增加安全架构图"]
    }}
    """
    
    def run(self, state: EvaluationState) -> EvaluationState:
        # 根据领域判断需要满足的合规标准
        regulations = self.get_regulations(state.analysis_result.domain_tags)
        
        result = self.llm.complete(
            self.SECURITY_PROMPT.format(
                planning_summary=self.summarize_planning(state.planning_result),
                regulations="、".join(regulations),
            ),
            response_format={"type": "json_object"}
        )
        state.security_report = json.loads(result.text)
        return state
```

### 7.3 综合评分模型

```python
class ScoringNode:
    """
    综合评分：加权各维度得分，生成最终评测报告
    
    扩展为 10 维评测体系：
    1. PRD覆盖率 (coverage)
    2. 内部一致性 (consistency)
    3. 技术可行性 (feasibility)
    4. 架构质量 (architecture_quality)
    5. 安全合规 (security)
    6. 成本合理性 (cost_reasonableness)     ← 新增
    7. 可实施性 (implementability)          ← 新增
    8. 可维护性 (maintainability)           ← 新增
    9. 技术先进性 (tech_advancement)        ← 新增
    10. 法律合规 (legal_compliance)         ← 新增
    """
    
    # 权重配置（可通过配置调整）
    WEIGHTS = {
        "coverage": 0.15,              # PRD 覆盖率
        "consistency": 0.12,           # 内部一致性
        "feasibility": 0.12,           # 技术可行性
        "architecture_quality": 0.12,  # 架构质量
        "security": 0.10,              # 安全合规
        "cost_reasonableness": 0.10,   # 成本合理性（新增）
        "implementability": 0.10,      # 可实施性（新增）
        "maintainability": 0.08,       # 可维护性（新增）
        "tech_advancement": 0.06,      # 技术先进性（新增）
        "legal_compliance": 0.05,      # 法律合规（新增）
    }
    
    def run(self, state: EvaluationState) -> EvaluationState:
        scores = {}
        
        # 1. Coverage (原有)
        cov = state.coverage_report
        scores["coverage"] = cov.get("overall_coverage_rate", 0) * 100
        
        # 2. Consistency (原有)
        con = state.consistency_report
        total_conflicts = len(con.get("conflicts", []))
        scores["consistency"] = max(0, 100 - total_conflicts * 10)
        
        # 3. Feasibility (原有)
        feas = state.feasibility_report
        scores["feasibility"] = feas.get("feasibility_score", 3) / 5 * 100
        
        # 4. Architecture Quality (原有)
        qual = state.quality_report
        scores["architecture_quality"] = qual.get("overall_quality", 3) / 5 * 100
        
        # 5. Security (原有)
        sec = state.security_report
        critical = len([i for i in sec.get("critical_issues", [])
                       if i.get("severity") == "high"])
        scores["security"] = max(0, 100 - critical * 20)
        
        # 6. Cost Reasonableness (新增)
        scores["cost_reasonableness"] = self.evaluate_cost_reasonableness(state)
        
        # 7. Implementability (新增)
        scores["implementability"] = self.evaluate_implementability(state)
        
        # 8. Maintainability (新增)
        scores["maintainability"] = qual.get("non_functional", {}).get("maintainability", 3) / 5 * 100
        
        # 9. Tech Advancement (新增)
        scores["tech_advancement"] = self.evaluate_tech_advancement(state)
        
        # 10. Legal Compliance (新增)
        scores["legal_compliance"] = self.evaluate_legal_compliance(state)
        
        # 加权总分
        total = sum(scores[k] * self.WEIGHTS[k] for k in self.WEIGHTS)
        
        # 生成结论
        if total >= 85:
            conclusion = "通过"
        elif total >= 70:
            conclusion = "预警通过"
        else:
            conclusion = "不通过"
        
        state.evaluation_report = EvaluationReport(
            overall_score=round(total, 1),
            dimension_scores=scores,
            conclusion=conclusion,
            p0_coverage=state.coverage_report.get("p0_coverage", 0),
            critical_issues=self.collect_critical_issues(state),
            recommendations=self.collect_recommendations(state),
            should_iterate=conclusion == "不通过",
            suggested_action="replan" if total < 70 else "regenerate",
        )
        return state
    
    def evaluate_cost_reasonableness(self, state: EvaluationState) -> float:
        """评估成本合理性"""
        cost = getattr(state, 'cost_report', {})
        if not cost:
            return 70  # 默认分
        # 与同类项目对比：成本在同类项目的 -20% ~ +20% 为合理
        deviation = abs(cost.get('cost_deviation', 0))
        if deviation < 0.2:
            return 90
        elif deviation < 0.5:
            return 70
        else:
            return 50
    
    def evaluate_implementability(self, state: EvaluationState) -> float:
        """评估可实施性（团队能力匹配度）"""
        score = state.feasibility_report.get("implementability", {}).get("score", 3)
        return score / 5 * 100
    
    def evaluate_tech_advancement(self, state: EvaluationState) -> float:
        """评估技术先进性（避免过时技术）"""
        # 检查技术栈中是否有已被社区淘汰的技术
        tech_stack = state.planning_result.tech_stack
        obsolete_techs = self.check_obsolete_technologies(tech_stack)
        if len(obsolete_techs) == 0:
            return 90
        elif len(obsolete_techs) <= 2:
            return 60
        else:
            return 40
    
    def evaluate_legal_compliance(self, state: EvaluationState) -> float:
        """评估法律合规性"""
        # 基于行业判断需要满足的法规
        industries = state.analysis_result.domain_tags
        regulations_needed = self.get_applicable_regulations(industries)
        regulations_met = state.security_report.get("regulations_met", [])
        
        if not regulations_needed:
            return 85  # 无特殊合规要求
        
        met_rate = len([r for r in regulations_needed if r in regulations_met]) / len(regulations_needed)
        return met_rate * 100
```

### 7.4 评分校准机制

```python
class ScoreCalibrator:
    """
    评分校准 - 消除 LLM 打分的偏差
    策略：人工校正 + 历史比对 + 平行评测 + A/B测试 + 反馈闭环
    """
    
    def __init__(self):
        self.history_store = ScoreHistoryStore()
    
    def calibrate(self, raw_scores: dict, 
                  task_id: str, workspace_id: str) -> dict:
        """多策略校准"""
        calibrations = []
        
        # 1. 历史比对校准
        hist_cal = self.historical_calibration(raw_scores, workspace_id)
        calibrations.append(hist_cal)
        
        # 2. 平行评测校准（多个LLM Judge取平均）
        if settings.ENABLE_PARALLEL_JUDGE:
            parallel_cal = self.parallel_judge_calibration(task_id)
            calibrations.append(parallel_cal)
        
        # 3. 综合校准结果
        calibrated = {}
        for dimension in raw_scores:
            values = [raw_scores[dimension]] + [c[dimension] for c in calibrations if dimension in c]
            calibrated[dimension] = sum(values) / len(values)
        
        return calibrated
    
    def historical_calibration(self, scores: dict, 
                               workspace_id: str) -> dict:
        """
        历史比对校准
        与同一工作空间的历史方案评分做归一化
        """
        history = self.history_store.get_recent_scores(workspace_id, limit=50)
        if len(history) < 5:
            return scores  # 历史数据不足，不校准
        
        calibrated = {}
        for dim in scores:
            hist_values = [h["dimension_scores"].get(dim, 0) for h in history]
            if not hist_values:
                calibrated[dim] = scores[dim]
                continue
            
            mean = statistics.mean(hist_values)
            std = statistics.stdev(hist_values) if len(hist_values) > 1 else 10
            z_score = (scores[dim] - mean) / max(std, 1)
            
            # 如果当前评分偏离历史均值超过2个标准差，向均值拉回
            if abs(z_score) > 2:
                calibrated[dim] = mean + (z_score * std * 0.5)  # 拉回50%
            else:
                calibrated[dim] = scores[dim]
        
        return calibrated
    
    def parallel_judge_calibration(self, task_id: str) -> dict:
        """
        平行评测 - 使用多个低成本LLM Judge独立评分后取平均
        """
        judges = ["gpt-4o-mini", "deepseek-v3"]
        all_scores = []
        
        for judge_model in judges:
            scores = self.run_judge(task_id, judge_model)
            all_scores.append(scores)
        
        # 取平均
        calibrated = {}
        for dim in all_scores[0]:
            values = [s[dim] for s in all_scores]
            calibrated[dim] = sum(values) / len(values)
        
        return calibrated
    
    def feedback_loop_update(self, task_id: str, 
                             user_rating: float):
        """
        反馈闭环 - 用户满意度回传，调整评分模型
        """
        # 1. 记录实际用户评分
        self.history_store.record_feedback(task_id, user_rating)
        
        # 2. 计算系统评分 vs 用户评分的偏差
        system_score = self.history_store.get_system_score(task_id)
        deviation = user_rating - system_score
        
        # 3. 如果偏差持续 > 15 分，触发权重调整
        recent_deviation = self.history_store.get_recent_deviation(limit=20)
        if abs(statistics.mean(recent_deviation)) > 15:
            self.adjust_weights(recent_deviation)
    
    def adjust_weights(self, deviations: list[float]):
        """基于反馈偏差调整权重"""
        # 如果用户评分持续低于系统评分，降低不信任维度的权重
        # 反之亦然
        avg_deviation = statistics.mean(deviations)
        if avg_deviation < -15:
            # 系统评分偏高，降低波动最大的维度权重
            logger.warning(f"系统评分持续偏高 {avg_deviation:.1f}分，自动调整权重")
            # 具体调整逻辑...
        elif avg_deviation > 15:
            logger.warning(f"系统评分持续偏低 {avg_deviation:.1f}分，自动调整权重")
```

### 7.5 评测 Graph 扩展

```python
# 新增评测节点
eval_graph.add_node("cost_eval", CostEvalNode())               # 成本合理性（新增）
eval_graph.add_node("implementability_eval", ImplementabilityEvalNode())  # 可实施性（新增）
eval_graph.add_node("maintainability_eval", MaintainabilityEvalNode())    # 可维护性（新增）
eval_graph.add_node("tech_advancement_eval", TechAdvancementEvalNode())   # 技术先进性（新增）
eval_graph.add_node("legal_compliance_eval", LegalComplianceEvalNode())   # 法律合规（新增）
eval_graph.add_node("score_calibrator", ScoreCalibratorNode())            # 评分校准（新增）

# 并行执行扩展维度
eval_graph.add_edge("security_compliance", "cost_eval")
eval_graph.add_edge("cost_eval", "implementability_eval")
eval_graph.add_edge("implementability_eval", "maintainability_eval")
eval_graph.add_edge("maintainability_eval", "tech_advancement_eval")
eval_graph.add_edge("tech_advancement_eval", "legal_compliance_eval")

# 评分校准在综合评分前执行
eval_graph.add_edge("legal_compliance_eval", "score_calibrator")
eval_graph.add_edge("score_calibrator", "scoring")
```

---

## 八、完整项目目录结构

```
prd2techspec/
├── docker-compose.yml                  # 完整部署编排
├── Dockerfile                          # API 服务
├── Dockerfile.celery                   # Celery Worker
├── pyproject.toml                      # Python 项目配置
├── alembic.ini                         # 数据库迁移
├── .env.example                        # 环境变量示例
├── .github/
│   └── workflows/
│       ├── ci.yml                      # CI/CD 流水线
│       ├── deploy-staging.yml          # 自动部署到测试环境
│       ├── deploy-prod.yml             # 手动触发生产部署
│       ├── knowledge-base-sync.yml     # 知识图谱定期更新
│       └── backup.yml                  # 定时备份
│
├── orchestrator/                       # ⭐ 顶层编排
│   ├── __init__.py
│   ├── main_graph.py                   # 四层串联的 StateGraph
│   ├── state.py                        # OrchestratorState（含租户上下文）
│   ├── routing.py                      # 条件路由逻辑
│   ├── human_review.py                 # Human-in-the-Loop 节点
│   └── iteration.py                    # 迭代决策
│
├── auth/                               # ⭐ 新增：认证与权限
│   ├── __init__.py
│   ├── models.py                       # 用户/角色/权限模型
│   ├── permissions.py                  # RBAC + ABAC 权限检查
│   ├── middleware.py                   # FastAPI 权限中间件
│   ├── token_manager.py                # JWT 管理
│   └── identity_providers/
│       ├── __init__.py
│       ├── keycloak.py                 # Keycloak SSO
│       ├── wecom.py                    # 企业微信
│       └── ldap.py                     # LDAP
│
├── knowledge_layer/                    # Layer 1: 知识层
│   ├── __init__.py
│   ├── config.py                       # Neo4j/PGVector/LLM 配置
│   ├── models.py                       # KGEntity, KGRelation 等
│   ├── pipeline.py                     # RetrievalPipeline 主入口
│   │
│   ├── ingestion/                      # 知识图谱构建
│   │   ├── __init__.py
│   │   ├── document_loader.py          # 多格式文档加载（集成 CSV）
│   │   ├── csv_loader.py               # ⭐⭐ CSV/TSV 专用加载器（行级+列级双通路索引）（新增）
│   │   ├── web_loader.py               # ⭐⭐ 网络资源加载器（URL抓取+Readability正文提取）（新增）
│   │   ├── web_crawler.py              # ⭐⭐ 同域递归爬虫（BFS+robots.txt+断点续爬）（新增）
│   │   ├── web_sync.py                 # ⭐⭐ 定时同步（ETag/哈希变更检测+Celery Beat）（新增）
│   │   ├── chunker.py                  # ⭐ 多粒度分块策略（Sentence/Paragraph/Section）
│   │   ├── text_unit_builder.py         # ⭐ TextUnit 中间层构建（新增）
│   │   ├── entity_extractor.py         # 实体提取
│   │   ├── relation_extractor.py       # 关系提取
│   │   ├── entity_resolver.py          # ⭐ 实体融合（新增）
│   │   ├── multimodal_extractor.py     # ⭐⭐ 多模态提取（管道A: 图片→文本+视觉向量双写）
│   │   ├── image_chunk_store.py        # ⭐⭐ ImageChunk 存储（视觉768d+文本768d双向量）
│   │   ├── claims_extractor.py          # ⭐ Claims/Covariates 提取（新增）
│   │   ├── entity_embedder.py           # ⭐ 实体多源融合 Embedding（新增）
│   │   ├── community_detector.py        # ⭐ Leiden 社区检测（新增）
│   │   ├── community_report_generator.py# ⭐ 社区摘要报告生成（新增）
│   │   ├── knowledge_aging.py          # ⭐ 知识老化策略（新增）
│   │   ├── kg_versioning.py            # ⭐ 知识图谱版本控制（新增）
│   │   └── index_builder.py            # PropertyGraphIndex 构建
│   │
│   └── retrieval/                      # ⭐ 多路检索
│       ├── __init__.py
│       ├── intent_router.py             # Intent Router（local/global/hybrid/visual路由）
│       ├── rewriter.py                 # Query Rewriter
│       ├── enricher.py                 # Query Enricher
│       ├── local_search.py             # ⭐ Local Search（实体匹配+子图遍历+TextUnit证据）
│       ├── global_search.py            # ⭐ Global Search（社区报告匹配+层级选择+LLM聚合）
│       ├── multimodal_search.py        # ⭐⭐ Multimodal Search（CLIP双塔+以图搜图+文搜图+图文混合）
│       ├── graph_search.py             # 图检索（子图遍历模式）
│       ├── vector_search.py            # 语义检索（多粒度 + 社区报告 + ImageChunk双向量匹配）
│       ├── bm25_search.py              # 全文检索
│       ├── fusion.py                   # RRF 融合
│       ├── reranker.py                 # Cross-encoder 重排
│       ├── compressor.py               # 上下文压缩
│       └── iterative.py                # 迭代检索 + 质量自评
│
├── analysis_layer/                     # Layer 2: 分析层
│   ├── __init__.py
│   ├── agent_graph.py                  # LangGraph 定义
│   ├── models.py                       # AnalysisResult 等
│   ├── tools.py                        # 分析用工具函数
│   │
│   └── nodes/
│       ├── __init__.py
│       ├── parse_node.py               # 文档解析
│       ├── lang_detector.py            # ⭐ 语言检测（新增）
│       ├── requirement_node.py          # 需求提取
│       ├── quality_scorer.py           # ⭐ 需求质量评分（新增）
│       ├── entity_extraction_node.py    # 实体提取
│       ├── constraint_node.py           # 约束分析
│       ├── dependency_node.py           # 依赖分析
│       ├── domain_classifier.py         # 领域分类
│       ├── clarity_checker.py           # 清晰度检查
│       ├── effort_estimator.py         # ⭐ 工作量估算（新增）
│       ├── stakeholder_analyzer.py     # ⭐ 干系人分析（新增）
│       └── result_assembler.py          # 结果组装
│
├── planning_layer/                     # Layer 3: 规划层
│   ├── __init__.py
│   ├── agent_graph.py                  # LangGraph 定义
│   ├── models.py                       # PlanningResult 等
│   ├── tools.py
│   │
│   └── nodes/
│       ├── __init__.py
│       ├── knowledge_augment.py         # 知识检索增强
│       ├── pattern_recommend.py         # 架构模式推荐
│       ├── pattern_confirm.py           # 模式确认
│       ├── tech_stack_select.py         # 技术栈选型
│       ├── component_decompose.py       # 组件分解
│       ├── cost_estimator.py            # ⭐ 成本估算（新增）
│       ├── timeline_planner.py          # ⭐ 时间线规划（新增）
│       ├── skill_gap_analyzer.py        # ⭐ 技能缺口分析（新增）
│       ├── risk_quantifier.py           # ⭐ 风险量化（新增）
│       ├── data_arch_design.py          # 数据架构
│       ├── api_planning.py              # API 规划
│       ├── deployment_planning.py       # 部署规划
│       ├── plan_self_check.py           # 规划自检
│       └── plan_assembler.py            # 整合输出
│
├── generation_layer/                   # Layer 4: 生成层
│   ├── __init__.py
│   ├── agent_graph.py                  # LangGraph 定义
│   ├── models.py                       # GenerationResult 等
│   ├── tools.py
│   │
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── outline_node.py             # 大纲生成
│   │   ├── section_writer.py           # 逐节撰写
│   │   ├── diagram_generator_node.py   # ⭐⭐ 架构图自动生成（管道B: 文本→Mermaid→PNG/SVG）
│   │   ├── code_scaffold_node.py        # 代码框架生成
│   │   ├── consistency_checker.py      # 一致性检查
│   │   ├── revision_node.py            # 修复节点
│   │   ├── format_assembler.py         # 格式组装
│   │   └── format_exporter.py          # ⭐⭐ 多格式导出（多模态增强: 嵌入PNG/SVG图表）
│   │
│   └── templates/                      # ⭐ 模板系统（新增）
│       ├── __init__.py
│       ├── engine.py                   # 模板引擎
│       ├── industry/                   # 行业模板
│       │   ├── ecommerce.yaml
│       │   ├── fintech.yaml
│       │   ├── healthcare.yaml
│       │   ├── iot.yaml
│       │   └── saas.yaml
│       ├── enterprise/                 # 企业模板
│       │   └── default.yaml
│       └── section/                    # 章节模板
│           ├── background.md
│           ├── architecture.md
│           ├── api_design.md
│           └── security.md
│
├── evaluation/                         # 评测体系
│   ├── __init__.py
│   ├── agent_graph.py                  # 评测 Agent
│   ├── models.py                       # EvaluationReport
│   ├── scoring.py                      # 综合评分（10维）
│   ├── score_calibrator.py             # ⭐ 评分校准（新增）
│   │
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── coverage.py                 # PRD覆盖率
│   │   ├── consistency.py              # 一致性
│   │   ├── feasibility.py              # 可行性
│   │   ├── architecture_quality.py     # 架构质量
│   │   ├── security_compliance.py      # 安全合规
│   │   ├── cost_eval.py                # ⭐ 成本合理性（新增）
│   │   ├── implementability_eval.py    # ⭐ 可实施性（新增）
│   │   ├── maintainability_eval.py     # ⭐ 可维护性（新增）
│   │   ├── tech_advancement_eval.py    # ⭐ 技术先进性（新增）
│   │   └── legal_compliance_eval.py    # ⭐ 法律合规（新增）
│   │
│   └── feedback/                       # 人工反馈
│       ├── feedback_collector.py       # 反馈采集
│       ├── feedback_store.py           # 反馈存储
│       └── feedback_sync.py            # 反馈→知识图谱同步
│
├── integrations/                       # ⭐ 新增：集成生态
│   ├── __init__.py
│   ├── hub.py                          # IntegrationHub
│   ├── jira.py                         # Jira 集成
│   ├── confluence.py                   # Confluence 集成
│   ├── github.py                       # GitHub 集成
│   ├── gitlab.py                       # GitLab 集成
│   ├── feishu.py                       # 飞书 集成
│   ├── dingtalk.py                     # 钉钉 集成
│   ├── wecom.py                        # 企业微信 集成
│   ├── slack.py                        # Slack 集成
│   └── webhook.py                      # Webhook 自定义集成
│
├── collaboration/                      # ⭐ 新增：协作文档
│   ├── __init__.py
│   ├── service.py                      # 协作服务
│   ├── comment.py                      # 评论管理
│   ├── suggestion.py                   # 建议修改
│   ├── changelog.py                    # 变更历史
│   └── notification.py                 # 通知服务
│
├── session_history/                    # ⭐⭐ 新增：会话历史管理
│   ├── __init__.py
│   ├── service.py                      # 会话历史服务（CRUD + 搜索）
│   ├── models.py                       # Session, SessionMessage 模型
│   ├── repository.py                   # 数据库访问层（分页/筛选/排序）
│   ├── search.py                       # 会话全文搜索（基于 PostgreSQL FTS）
│   ├── exporter.py                     # 会话导出（Markdown / JSON / PDF）
│   ├── summarizer.py                   # LLM自动生成会话摘要和标签
│   └── cleanup.py                      # 会话老化清理策略
│
├── document_management/                # ⭐⭐ 新增：已上传文档管理
│   ├── __init__.py
│   ├── service.py                      # 文档管理服务（上传/列表/删除/重索引）
│   ├── models.py                       # UploadedDocument 模型
│   ├── repository.py                   # 数据库访问层
│   ├── search.py                       # 文档内容搜索（文件名+全文+向量混合）
│   ├── preview.py                      # 文档预览生成（PDF缩略图/Markdown渲染/CSV表格预览）
│   ├── deduplication.py                # 文件去重（SHA-256哈希比对）
│   ├── batch_operations.py             # 批量导入/导出/删除
│   └── storage.py                      # 存储后端抽象（MinIO / 本地 / S3）
│
├── security/                           # ⭐ 新增：数据安全
│   ├── __init__.py
│   ├── data_masking.py                 # 数据脱敏引擎
│   ├── audit_logger.py                 # 审计日志（哈希链）
│   ├── data_classifier.py              # 数据分类分级
│   └── encryption.py                   # 加密工具
│
├── api/                                # FastAPI 服务
│   ├── __init__.py
│   ├── main.py                         # 应用入口
│   ├── deps.py                         # 依赖注入
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── generate.py                 # 方案生成接口
│   │   ├── evaluate.py                 # 评测接口
│   │   ├── knowledge.py                # 知识管理接口
│   │   ├── feedback.py                 # 反馈接口
│   │   ├── review.py                   # 人工审核接口
│   │   ├── auth.py                     # ⭐ 认证接口（新增）
│   │   ├── workspace.py                # ⭐ 工作空间接口（新增）
│   │   ├── sessions.py                 # ⭐⭐ 会话历史接口（新增）
│   │   ├── documents.py                # ⭐⭐ 已上传文档管理接口（新增）
│   │   ├── collaboration.py            # ⭐ 协作接口（新增）
│   │   ├── integrations.py             # ⭐ 集成接口（新增）
│   │   └── export.py                   # ⭐ 导出接口（新增）
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── request.py                  # 请求模型
│   │   └── response.py                 # 响应模型
│   │
│   └── tasks.py                        # Celery 异步任务
│
├── llm_gateway/                        # ⭐ 新增：LLM Gateway
│   ├── __init__.py
│   ├── router.py                       # 模型路由策略
│   ├── cost_tracker.py                 # 成本追踪
│   ├── budget_controller.py            # 预算控制
│   ├── rate_limiter.py                 # 流控
│   ├── cache.py                        # 语义缓存
│   ├── fallback.py                     # 降级策略
│   └── observability.py                # LangFuse/LangSmith集成
│
├── observability/                      # ⭐ 新增：观测性
│   ├── __init__.py
│   ├── tracing.py                      # OpenTelemetry 分布式追踪
│   ├── metrics.py                      # Prometheus 指标定义
│   ├── alerts.yml                      # 告警规则
│   └── dashboards/                     # Grafana 面板配置
│       └── prd2techspec.json
│
├── webui/                              # Streamlit 前端（可选）
│   ├── app.py
│   ├── pages/
│   │   ├── generate.py
│   │   ├── knowledge.py
│   │   ├── history.py
│   │   ├── evaluation.py
│   │   ├── workspace.py                # ⭐ 工作空间管理（新增）
│   │   └── collaboration.py            # ⭐ 协作（新增）
│   └── components/
│       ├── architecture_viewer.py
│       ├── diff_viewer.py
│       └── gantt_chart.py              # ⭐ 甘特图（新增）
│
├── core/                               # 核心基础设施
│   ├── __init__.py
│   ├── config.py                       # 全局配置（pydantic-settings）
│   ├── llm.py                          # LLM 客户端（多模型支持）
│   ├── logger.py                       # 结构化日志
│   ├── metrics.py                      # 监控指标
│   └── exceptions.py                   # 自定义异常
│
├── storage/                            # 本地存储目录
│   ├── kg_index/                       # LlamaIndex 持久化
│   ├── kg_snapshots/                   # ⭐ 知识图谱版本快照（新增）
│   └── uploads/                        # 上传文档临时存储
│
├── scripts/                            # 运维脚本
│   ├── init_knowledge.py               # 初始化知识图谱
│   ├── seed_data.py                    # 种子数据导入
│   ├── backup.sh                       # 备份
│   ├── restore.sh                      # ⭐ 恢复（新增）
│   └── migrate.sh                      # 数据库迁移
│
├── tests/                              # 测试
│   ├── unit/
│   │   ├── test_knowledge_layer/
│   │   ├── test_analysis_layer/
│   │   ├── test_planning_layer/
│   │   ├── test_generation_layer/
│   │   ├── test_evaluation/
│   │   ├── test_auth/                  # ⭐ 新增
│   │   ├── test_security/              # ⭐ 新增
│   │   └── test_integrations/          # ⭐ 新增
│   ├── integration/
│   │   ├── test_pipeline.py
│   │   ├── test_orchestrator.py
│   │   └── test_auth_flow.py           # ⭐ 新增
│   └── e2e/
│       └── test_full_flow.py
│
├── monitoring/                         # ⭐ 监控配置（新增）
│   ├── prometheus.yml
│   ├── alerts.yml
│   └── grafana/
│       └── dashboards/
│           └── prd2techspec.json
│
└── docs/                               # 文档
    ├── architecture.md                 # 本架构文档
    ├── evaluation.md                   # 评测体系
    ├── deployment.md                   # 部署指南
    ├── api_reference.md                # API 文档
    ├── user_guide.md                   # 用户指南
    ├── security.md                     # ⭐ 安全指南（新增）
    └── integration_guide.md            # ⭐ 集成指南（新增）
```

---

## 九、部署方案（完整版）

### 9.1 Docker Compose 完整服务列表

```yaml
version: '3.8'

services:
  # === 基础设施 ===
  neo4j:
    image: neo4j:5-enterprise  # 或 community
    ports: ["7687:7687", "7474:7474"]
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    volumes: ["./data/neo4j:/data", "./data/neo4j/logs:/logs"]
    deploy:
      resources: {limits: {memory: "4G"}}
  
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: prd2techspec
      POSTGRES_USER: ${PG_USER}
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    volumes: ["./data/postgres:/var/lib/postgresql/data"]
    command: ["postgres", "-c", "shared_prefs=512MB", "-c", "effective_csize=1GB"]
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["./data/redis:/data"]
  
  minio:
    image: minio/minio
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: ${MINIO_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD}
    command: server /data --console-address ":9001"
    volumes: ["./data/minio:/data"]
  
  # === ⭐ 新增：SSO / 身份认证 ===
  keycloak:
    image: quay.io/keycloak/keycloak:24.0
    ports: ["8080:8080"]
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: ${KEYCLOAK_PASSWORD}
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgres/keycloak
      KC_DB_USERNAME: ${PG_USER}
      KC_DB_PASSWORD: ${PG_PASSWORD}
    command: start-dev
    depends_on: [postgres]
    deploy:
      resources: {limits: {memory: "2G"}}
  
  # === ⭐ 新增：LLM 可观测 ===
  langfuse:
    image: ghcr.io/langfuse/langfuse:latest
    ports: ["3002:3000"]
    environment:
      DATABASE_URL: postgresql://${PG_USER}:${PG_PASSWORD}@postgres/langfuse
      NEXTAUTH_SECRET: ${LANGFUSE_SECRET}
    depends_on: [postgres]
  
  # === ⭐⭐ 新增：网络爬虫代理（可选，用于访问受限站点）===
  # 如需抓取某些限制区域的网站，可在此配置代理
  # 无需代理时注释掉此块
  # crawler-proxy:
  #   image: squid:latest
  #   ports: ["3128:3128"]
  #   volumes: ["./proxy/squid.conf:/etc/squid/squid.conf"]

  # === 应用服务 ===
  api:
    build: 
      context: .
      dockerfile: Dockerfile
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [neo4j, postgres, redis, minio, keycloak]
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
    volumes: ["./storage:/app/storage"]
    deploy:
      resources: {limits: {memory: "4G", cpus: "2"}}
  
  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile.celery
    env_file: .env
    depends_on: [neo4j, postgres, redis, minio]
    command: celery -A api.tasks worker --loglevel=info --concurrency=2
    volumes: ["./storage:/app/storage"]
    deploy:
      resources: {limits: {memory: "8G", cpus: "2"}}  # 需要更多资源
  
  # === ⭐⭐ 新增：图表渲染服务（多模态管道B）===
  kroki:
    image: yuzutech/kroki:latest
    ports: ["8001:8001"]
    environment:
      KROKI_MERMAIR_URL: http://mermaid:8002
    depends_on: [mermaid]
  
  mermaid:
    image: yuzutech/kroki-mermaid:latest
    ports: ["8002:8002"]

  # === 监控 ===
  jaeger:                                   # ⭐ 分布式追踪（新增）
    image: jaegertracing/all-in-one:latest
    ports: ["4317:4317", "16686:16686"]
  
  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]
    volumes: ["./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml"]
  
  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
    volumes: ["./data/grafana:/var/lib/grafana"]
  
  # === ⭐ 新增：备份 ===
  backup:
    image: alpine:latest
    volumes:
      - "./data:/data:ro"
      - "./backups:/backups"
      - "/var/run/docker.sock:/var/run/docker.sock"
    command: |
      sh -c "apk add --no-cache postgresql-client mysql-client &&
      while true; do
        pg_dump -h postgres -U ${PG_USER} prd2techspec > /backups/pg_\$(date +%Y%m%d_%H%M%S).dump &&
        sleep 86400
      done"
    depends_on: [postgres]
```

### 9.2 API 接口完整列表

```python
# === 核心流程 ===
POST /api/v1/generate
    提交 PRD，生成技术方案（异步）
    Request: {prd_content: str, prd_type: str, options: GenerateOptions}
    Response: {task_id: str, status: "pending"}

GET  /api/v1/tasks/{task_id}
    查询任务状态和结果
    Response: {task_id, status, progress, result: GenerationResult}

POST /api/v1/generate/sync
    同步模式（仅适合短 PRD）
    Request: {prd_content: str}
    Response: {result: GenerationResult, evaluation: EvaluationReport}

# === 人工审核 ===
GET  /api/v1/review/pending
    获取所有待审核事项
    Response: [{task_id, stage, content, questions}]

POST /api/v1/review/{task_id}/{stage}
    提交人工审核意见
    Request: {approved: bool, feedback: str, suggestions: list[str]}
    Response: {status: "submitted"}

# === 知识管理 ===
POST /api/v1/knowledge/documents
    上传文档到知识图谱（支持 .md/.pdf/.docx/.txt/.csv/.tsv）
    Request: multipart/form-data (文件)
    Response: {doc_id: str, entity_count: int, status: "indexing"}

POST /api/v1/knowledge/web-page                      # ⭐⭐ 新增
    索引单个网络资源
    Request: {url: str, auto_refresh: bool?}
    Response: {resource_id: str, title: str, status: "indexed"}

POST /api/v1/knowledge/web-crawl                     # ⭐⭐ 新增
    递归爬取同域页面
    Request: {seed_url: str, max_depth: int, max_pages: int, 
              include_patterns: list[str]?, exclude_patterns: list[str]?}
    Response: {job_id: str, status: "running"}

GET  /api/v1/knowledge/web-crawl/{job_id}             # ⭐⭐ 新增
    查询爬取任务状态
    Response: {job_id, status, pages_fetched, pages_total, completed_at}

POST /api/v1/knowledge/web-sync                       # ⭐⭐ 新增
    配置定时同步
    Request: {resource_id: str, cron_expression: str, notify_on_change: bool?}
    Response: {sync_id: str, next_sync_at: str}

DELETE /api/v1/knowledge/web-sync/{sync_id}           # ⭐⭐ 新增
    取消定时同步

GET  /api/v1/knowledge/search
    知识图谱搜索（调试用）
    Request: {query: str, mode: str}
    Response: {results: list, confidence: float}

POST /api/v1/knowledge/entities
    手动添加实体
    Request: [Entity]
    Response: {added: int}

DELETE /api/v1/knowledge/entities/{entity_id}

# === ⭐⭐ 新增：会话历史管理 ===
GET  /api/v1/sessions
    获取会话历史列表
    Request Query: {workspace_id, page, page_size, status, session_type, 
                    q(搜索关键词), sort_by(created_at/updated_at/last_message_at), 
                    sort_order(asc/desc), tags, date_from, date_to}
    Response: {items: [Session], total: int, page: int, page_size: int}

POST /api/v1/sessions
    创建新会话
    Request: {workspace_id: str, title: str, session_type: str, 
              source_prd_id: str?, tags: list[str]?}
    Response: {session: Session}

GET  /api/v1/sessions/{session_id}
    获取会话详情（含会话摘要信息，不含完整消息列表）
    Response: {session: Session}

PUT  /api/v1/sessions/{session_id}
    更新会话信息（标题/标签/评分等）
    Request: {title: str?, tags: list[str]?, rating: int?, summary: str?}
    Response: {session: Session}

DELETE /api/v1/sessions/{session_id}
    删除会话（软删除）
    Response: {status: "deleted"}

POST /api/v1/sessions/{session_id}/archive
    归档会话
    Response: {status: "archived"}

POST /api/v1/sessions/{session_id}/restore
    恢复已归档会话
    Response: {status: "restored"}

GET  /api/v1/sessions/{session_id}/messages
    获取会话消息列表（按 turn_index 排序）
    Request Query: {page, page_size, role?}
    Response: {items: [SessionMessage], total: int}

POST /api/v1/sessions/{session_id}/messages
    向会话中添加消息
    Request: {role: str, content: str, content_type: str?, 
              attachments: list[dict]?, parent_message_id: str?}
    Response: {message: SessionMessage}

GET  /api/v1/sessions/{session_id}/export
    导出会话历史
    Request Query: {format: "markdown"|"json"|"pdf"}
    Response: 文件下载 / JSON数据

POST /api/v1/sessions/batch-delete
    批量删除会话
    Request: {session_ids: list[str]}
    Response: {deleted_count: int}

POST /api/v1/sessions/search
    高级搜索会话（全文搜索消息内容）
    Request: {workspace_id: str, query: str, date_from: str?, date_to: str?,
              session_types: list[str]?, tags: list[str]?}
    Response: {items: [SearchResult], total: int}

# === ⭐⭐ 新增：已上传文档管理 ===
GET  /api/v1/documents
    获取已上传文档列表
    Request Query: {workspace_id, page, page_size, file_type, 
                    processing_status, q(搜索关键词), tags, 
                    sort_by(created_at/file_size/title), date_from, date_to}
    Response: {items: [UploadedDocument], total: int, page: int, page_size: int}

POST /api/v1/documents/upload
    上传文档（支持 .md/.pdf/.docx/.txt/.csv/.tsv/.png/.jpg）
    Request: multipart/form-data (文件) + metadata(workspace_id, tags?, session_id?)
    Response: {document: UploadedDocument, status: "pending"}

GET  /api/v1/documents/{document_id}
    获取文档详情（含处理状态、提取统计等）
    Response: {document: UploadedDocument}

GET  /api/v1/documents/{document_id}/content
    获取文档内容（文本提取结果）
    Request Query: {format: "markdown"|"text"|"html"?}
    Response: 文档文本内容（Markdown/纯文本）

GET  /api/v1/documents/{document_id}/preview
    获取文档预览（缩略图/前几页/表格前20行）
    Response: {preview: {type, data, page_count?, row_count?}}

PUT  /api/v1/documents/{document_id}
    更新文档信息（标题/描述/标签）
    Request: {title: str?, description: str?, tags: list[str]?}
    Response: {document: UploadedDocument}

DELETE /api/v1/documents/{document_id}
    删除文档（软删除，同时标记关联知识图谱实体）
    Response: {status: "deleted"}

POST /api/v1/documents/{document_id}/reindex
    重新索引文档到知识图谱
    Response: {status: "indexing", task_id: str}

POST /api/v1/documents/batch-delete
    批量删除文档
    Request: {document_ids: list[str]}
    Response: {deleted_count: int}

POST /api/v1/documents/batch-reindex
    批量重新索引
    Request: {document_ids: list[str]}
    Response: {task_ids: list[str]}

GET  /api/v1/documents/search
    搜索已上传文档（文件名+全文+语义混合搜索）
    Request: {workspace_id: str, query: str, file_type: str?, 
              use_semantic: bool?}
    Response: {items: [ScoredDoc]}

GET  /api/v1/documents/stats
    获取工作空间文档统计
    Request Query: {workspace_id}
    Response: {total: int, by_type: dict, by_status: dict, 
               total_size: int, recent_uploads: int}

# === 评测 ===
POST /api/v1/evaluate
    对已有方案进行评测
    Request: {planning_result: PlanningResult, analysis_result: AnalysisResult}
    Response: {evaluation: EvaluationReport}

# === 反馈 ===
POST /api/v1/feedback
    提交人工反馈
    Request: {task_id: str, rating: int, comments: str, corrections: str}
    Response: {status: "applied"}

# === ⭐ 新增：认证 ===
POST /api/v1/auth/login
    用户登录
    Request: {email: str, password: str}
    Response: {access_token: str, refresh_token: str, user: UserInfo}

POST /api/v1/auth/refresh
    刷新 Token
    Request: {refresh_token: str}
    Response: {access_token: str, refresh_token: str}

POST /api/v1/auth/logout
    登出
    Request: {refresh_token: str}
    Response: {status: "ok"}

GET  /api/v1/auth/me
    获取当前用户信息
    Response: {id, email, name, avatar, role, permissions}

# === ⭐ 新增：工作空间管理 ===
POST /api/v1/workspaces
    创建工作空间
    Request: {name: str, slug: str, description: str}
    Response: {workspace_id: str, status: "created"}

GET  /api/v1/workspaces
    列出用户的工作空间
    Response: [{workspace_id, name, role, member_count}]

GET  /api/v1/workspaces/{workspace_id}
    获取工作空间详情
    Response: {id, name, settings, members: [...], stats: {...}}

PUT  /api/v1/workspaces/{workspace_id}
    更新工作空间设置
    Request: {settings: {...}}

DELETE /api/v1/workspaces/{workspace_id}
    删除工作空间

POST /api/v1/workspaces/{workspace_id}/members
    添加团队成员
    Request: {email: str, role_id: str}

DELETE /api/v1/workspaces/{workspace_id}/members/{user_id}
    移除团队成员

# === ⭐ 新增：协作 ===
POST /api/v1/collaboration/comments
    添加评论
    Request: {doc_id: str, section_id: str, content: str, parent_id: str?}
    Response: {comment_id: str, created_at}

GET  /api/v1/collaboration/comments/{doc_id}
    获取文档评论列表
    Response: [{id, user, content, replies: [...], created_at}]

POST /api/v1/collaboration/suggestions
    提交建议修改
    Request: {doc_id: str, section_id: str, original: str, suggestion: str, reason: str}

GET  /api/v1/collaboration/history/{doc_id}
    获取变更历史
    Response: [{version, user, timestamp, change_summary}]

# === ⭐ 新增：导出 ===
POST /api/v1/export/{task_id}
    导出技术方案
    Request: {format: "pdf"|"docx"|"html"|"confluence"|"notion", options: {...}}
    Response: {download_url: str}  # 或 Confluence/Notion 页面URL

# === ⭐ 新增：集成配置 ===
POST /api/v1/integrations/{type}
    配置外部集成（jira/confluence/feishu/...）
    Request: {config: {api_url, token, ...}}

GET  /api/v1/integrations
    列出已配置的集成
    Response: [{type, status, last_sync_at}]

POST /api/v1/integrations/{type}/sync
    手动触发同步

# === ⭐ 新增：LLM 可观测 ===
GET  /api/v1/observability/costs
    获取成本报表
    Response: {daily: [...], monthly: {...}, by_model: {...}, by_layer: {...}}

GET  /api/v1/observability/traces/{task_id}
    获取任务全链路追踪
    Response: {spans: [{name, duration, input_preview, output_preview}]}

# === ⭐ 新增：知识图谱版本 ===
POST /api/v1/knowledge/versions
    创建知识图谱快照
    Response: {version_id: str}

POST /api/v1/knowledge/versions/{version_id}/rollback
    回滚到指定版本
    Response: {status: "rolled_back", version_id}

GET  /api/v1/knowledge/versions
    列出所有版本
    Response: [{version_id, created_at, reason, entity_count}]
```

### 9.3 部署架构图

```
                          ┌──────────────┐
                          │   Nginx/LB   │
                          │   (反向代理)  │
                          └──────┬───────┘
                                 │
                    ┌────────────┼────────────────┐
                    │            │                │
              ┌─────▼────┐ ┌────▼────┐     ┌─────▼─────┐
              │  API     │ │  API    │     │  Keycloak  │
              │  Pod 1   │ │  Pod 2  │     │  (SSO)     │
              └────┬─────┘ └────┬────┘     └───────────┘
                   │            │
              ┌────┴────────────┴────────────────────────┐
              │           Celery Worker                   │
              │      (异步方案生成任务)                     │
              └────────────────┬──────────────────────────┘
                               │
    ┌──────────┬──────────┬────┴────┬──────────┬──────────┬──────────┬──────────┬──────────┐
    │          │          │         │          │          │          │          │          │
┌───▼──┐  ┌───▼──┐  ┌───▼───┐ ┌───▼──┐  ┌───▼──┐  ┌───▼──┐  ┌───▼──┐  ┌───▼──┐  ┌───▼──┐
│Neo4j │  │Post- │  │ Redis │ │MinIO │  │Pro-  │  │Grafana│  │Jaeger│  │Lang- │  │⭐Kroki│
│      │  │gres  │  │       │ │      │  │me-   │  │       │  │追踪  │  │Fuse  │  │图表  │
│图数据│  │向量+ │  │缓存+ │ │文档  │  │theus │  │监控  │  │      │  │LLM   │  │渲染  │
│库    │  │业务  │  │队列  │ │存储  │  │      │  │面板  │  │      │  │观测  │  │      │
└──────┘  └──────┘  └──────┘ └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘
```

---

## 十、关键数据流（端到端 — ⭐⭐⭐ 完整多模态+多格式版）

```
                        ╔═══ 支持的数据源类型 ═══╗
                        ║                         ║
                        ║  ┌─────────────────┐    ║
                        ║  │ 本地文件上传      │    ║
                        ║  │  .md / .pdf      │    ║
                        ║  │  .docx / .txt    │    ║
                        ║  │  ⭐⭐ .csv/.tsv  │    ║
                        ║  │  图片/架构图     │    ║
                        ║  └────────┬────────┘    ║
                        ║           │             ║
                        ║  ┌────────▼────────┐    ║
                        ║  │ ⭐⭐ 网络资源    │    ║
                        ║  │ 方式A: 单次URL  │    ║
                        ║  │ 方式B: 递归爬取 │    ║
                        ║  │ 方式C: 定时同步 │    ║
                        ║  └────────┬────────┘    ║
                        ║           │             ║
                        ║  ┌────────▼────────┐    ║
                        ║  │ 搜索引擎回退     │    ║
                        ║  │ (本地无结果时    │    ║
                        ║  │ 自动触发)       │    ║
                        ║  └─────────────────┘    ║
                        ╚═════════════════════════╝
                                      │
  ┌──────────────────────────────────┼──────────────────────────────────┐
  │                   按类型分流（DocumentLoader）                      │
  │                                                                     │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
  │  │ 叙事文档  │  │ ⭐⭐ CSV  │  │ ⭐⭐ Web │  │ 图片/多模态      │   │
  │  │ .md/.pdf │  │ .csv/.tsv│  │ 页面/API │  │ 架构图/流程图    │   │
  │  │ .docx    │  │          │  │          │  │                  │   │
  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘   │
  │       │             │             │                  │             │
  │       ▼             ▼             ▼                  ▼             │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
  │  │标准分块  │  │CSV双通路 │  │Readability│  │ GPT-4o/CLIP     │   │
  │  │3级粒度   │  │行级+列级 │  │正文提取  │  │ 视觉提取+向量化  │   │
  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘   │
  │       └──────────────┴────────────┴──────────────────┘             │
  └────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                              [数据脱敏引擎]
                                      │
                                      ▼
                          [多租户上下文注入]
                                      │
                                      ▼
Layer 1: Knowledge Retrieval
  │  
  │  ┌─── 离线：知识图谱构建 ───────────────────────────────────────┐
  │  │  Document → Multi-Granularity Chunk (3级)                     │
  │  │  → Entity Extraction → Entity Resolution                      │
  │  │  → Relation Extraction                                        │
  │  │  → TextUnit Building (中间层)                                  │
  │  │  → Claims/Covariates Extraction                               │
  │  │  → Entity Embedding (多源融合)                                │
  │  │  → ⭐⭐ CLIP 视觉 Embedding (ImageChunk 双向量: 视觉768d+文本768d) │
  │  │  → ⭐⭐ 多模态图片提取 (GPT-4o视觉 → 结构化知识 → Neo4j + 向量双写) │
  │  │  → ⭐⭐ CSV 列级 Embedding + 行级 TextUnit                     │
  │  │  → ⭐⭐ Web 页面标题/描述/正文 Embedding                        │
  │  │  → Leiden Community Detection (多层级)                         │
  │  │  → Community Report Generation → Vector Store                 │
  │  │  → Neo4j + PGVector(含ImageChunk/CSV行列/Web页面) + 版本快照   │
  │  └──────────────────────────────────────────────────────────────┘
  │  
  │  ┌─── 在线：多路检索（⭐⭐⭐ 新增 web 路由）─────────────────────┐
  │  │  Intent Router → Query Rewriter (3条) → Query Enricher       │
  │  │  → [Router: local / global / hybrid / ⭐⭐ visual / ⭐⭐ web]   │
  │  │  ┌─ Local Search ────────────────────────────────────────┐   │
  │  │  │  实体匹配(精确+语义) → 子图遍历(1-2跳)                  │   │
  │  │  │  → TextUnit召回(原文证据) → Claims召回(声明断言)       │   │
  │  │  │  → 上下文组装                                          │   │
  │  │  └────────────────────────────────────────────────────────┘   │
  │  │  ┌─ Global Search ───────────────────────────────────────┐   │
  │  │  │  社区报告匹配(向量) → 层级选择(Level 0→N)              │   │
  │  │  │  → 跨社区洞察收集 → LLM聚合生成答案                    │   │
  │  │  └────────────────────────────────────────────────────────┘   │
  │  │  ┌─ ⭐⭐ Multimodal Search ──────────────────────────────┐   │
  │  │  │  CLIP 双塔编码 (visual_emb + text_emb 同一空间)        │   │
  │  │  │  ├─ 以图搜图: 上传图片 → PGVector ImageChunk 检索      │   │
  │  │  │  ├─ 文搜图:  文字描述 → CLIP text_emb → 找匹配架构图   │   │
  │  │  │  └─ 图文混合: query + image → RRF 融合排序            │   │
  │  │  └────────────────────────────────────────────────────────┘   │
  │  │  → RRF Fusion (含多模态 RRF)                                  │
  │  │  → Cross-encoder Re-rank                                     │
  │  │  → Context Compression → Self-Evaluation                      │
  │  └──────────────────────────────────────────────────────────────┘
  │
  ▼
Layer 2: Analysis
  │  Language Detection → PRD Parse (多格式+多语言+图片)
  │  → ⭐⭐ Multimodal Knowledge Extract (图片→结构化实体+关系)
  │  → Requirement Extraction → Entity Extraction
  │  → Constraint Analysis → Dependency Analysis
  │  → Domain Classification → Clarity Check
  │  → [可能需要追问用户]
  │  → Requirement Quality Scoring → Effort Estimation
  │  → Stakeholder Analysis
  │  → AnalysisResult (结构化输出 + ImageChunk 引用)
  │
  ▼
Layer 3: Planning
  │  [Human-in-the-Loop: 分析结果人工审核（可选）]
  │  Knowledge Augment → Pattern Recommend (2-3候选)
  │  → Pattern Confirm → Tech Stack Selection (按维度分批)
  │  → Component Decomposition
  │  → Cost Estimation (3种方案: 低成本/标准/高可用)
  │  → Timeline Planning (甘特图+里程碑)
  │  → Skill Gap Analysis (培训/招聘建议)
  │  → Risk Quantification (概率×影响矩阵)
  │  → Data Architecture → API Planning → Deployment Planning
  │  → Plan Self-Check → [不通过则回退]
  │  → PlanningResult
  │
  ▼
Layer 4: Generation (⭐⭐ 多模态输出)
  │  [Human-in-the-Loop: 架构方案人工审核（可选）]
  │  Template Selection (行业/企业匹配)
  │  → Outline Generation (模板驱动)
  │  → Section Writing (并行多节, 模板渲染)
  │  → ⭐⭐ Diagram Generation (管道B: 组件→Mermaid→PNG/SVG)
  │       ├─ 架构图 (components + relations → flowchart)
  │       ├─ 数据流图 (data_flows → sequence diagram)
  │       ├─ 部署拓扑图 (deployment → deployment diagram)
  │       └─ ER 图 (data models → erDiagram)
  │  → Code Scaffold Generation (可运行骨架)
  │  → Consistency Check (含图表一致性校验)
  │  → [不通过则修复]
  │  → Format Assembly (Mermaid + base64 PNG 内嵌)
  │  → ⭐⭐ Multi-Format Export (Markdown含Mermaid / PDF含PNG / DOCX含图 / HTML含SVG)
  │  → GenerationResult (含 generated_diagrams 字典)
  │
  ▼
Evaluation System (10维)
  │  PRD Coverage → Internal Consistency → Feasibility
  │  → Architecture Quality → Security Compliance
  │  → Cost Reasonableness → Implementability
  │  → Maintainability → Tech Advancement → Legal Compliance
  │  → Score Calibration (历史比对/平行评测/A/B测试)
  │  → Scoring (加权总分)
  │
  ▼
  ┌─────────┬─────────┬──────────┐
  │ pass    │ warning │  fail    │
  ▼         ▼         ▼          ▼
交付方案  预警交付  回退迭代   人工介入
  │         │                    │
  ▼         ▼                    ▼
[多格式导出] [通知干系人]   [自动创建Jira/飞书任务]
  │
  ├── 同步到Confluence/Notion
  ├── 发送Webhook通知
  └── 写入审计日志 (不可篡改哈希链)
  
  ┌─────────────────────────────────────┐
  │         反馈闭环                     │
  │  用户满意度 → 评分校准 → 权重调整    │
  │  → 知识图谱增强 → 下一次更好         │
  └─────────────────────────────────────┘
```

---

## 十一、数据安全与隐私（生产级）

### 11.1 数据分类与分级管控

```
数据安全等级矩阵：
┌──────────┬──────────────────┬──────────────────┬──────────────────┐
│ 等级     │ 定义             │ 示例             │ 管控要求          │
├──────────┼──────────────────┼──────────────────┼──────────────────┤
│ L1 公开  │ 可对外公开       │ 技术方案(脱敏后)  │ 无特殊限制        │
│ L2 内部  │ 仅团队内部       │ PRD(不含客户数据)│ 访问控制+审计     │
│ L3 敏感  │ 含客户/商业数据  │ PRD(含API Key)   │ 加密存储+传输+审计 │
│ L4 绝密  │ 战略级信息       │ 公司战略PRD      │ 完全隔离+专人审批  │
└──────────┴──────────────────┴──────────────────┴──────────────────┘
```

### 11.2 数据脱敏引擎

```python
class DataMaskingEngine:
    """
    自动检测并替换敏感信息
    在 PRD 进入任何 LLM 或存储前执行
    """
    
    PATTERNS = {
        "api_key":       re.compile(r'[A-Za-z0-9_-]{20,}'),
        "token":         re.compile(r'(Bearer|Token)\s+[A-Za-z0-9._-]+'),
        "password":      re.compile(r'password[=:]\s*\S+', re.IGNORECASE),
        "email":         re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
        "phone":         re.compile(r'1[3-9]\d{9}'),
        "id_card":       re.compile(r'\d{17}[\dXx]'),
        "ip_address":    re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'),
        "internal_url":  re.compile(r'(https?://)?([\w-]+\.)?internal\.\w+'),
    }
    
    def mask(self, text: str, level: str = "L2") -> str:
        """根据安全等级执行脱敏"""
        if level == "L1":
            # 公开：仅脱敏 API Key 和 Token
            sensitive_types = ["api_key", "token"]
        elif level == "L2":
            # 内部：脱敏凭证类信息
            sensitive_types = ["api_key", "token", "password", "internal_url"]
        elif level in ("L3", "L4"):
            # 敏感/绝密：全部脱敏
            sensitive_types = list(self.PATTERNS.keys())
        else:
            return text
        
        for stype in sensitive_types:
            pattern = self.PATTERNS[stype]
            text = pattern.sub(self._replacer(stype), text)
        
        return text
    
    def _replacer(self, stype: str) -> Callable:
        def replace(match: re.Match) -> str:
            return f"[MASKED_{stype.upper()}]"
        return replace
```

### 11.3 审计日志（不可篡改）

```sql
CREATE TABLE audit_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id      UUID REFERENCES users(id),
    actor_name    VARCHAR(128),
    action        VARCHAR(64) NOT NULL,  -- 'create' / 'read' / 'update' / 'delete' / 'export' / 'share'
    resource_type VARCHAR(64) NOT NULL,  -- 'prd' / 'scheme' / 'knowledge_entity' / 'workspace'
    resource_id   UUID,
    detail        JSONB,                 -- 操作详情（含变更前后对比）
    ip_address    INET,
    user_agent    TEXT,
    workspace_id  UUID REFERENCES workspaces(id),
    
    -- 哈希链保证不可篡改
    previous_hash VARCHAR(64),           -- 上一条审计日志的 SHA-256
    current_hash  VARCHAR(64) NOT NULL   -- SHA-256(previous_hash + timestamp + action + detail)
);

-- 审计日志写入（带哈希链）
async def write_audit_log(session: AsyncSession, log: AuditLog) -> AuditLog:
    # 获取上一条日志的哈希
    last_log = await session.execute(
        text("SELECT current_hash FROM audit_logs ORDER BY timestamp DESC LIMIT 1")
    )
    previous_hash = last_log.scalar() or "0" * 64
    
    # 计算当前哈希
    raw = f"{previous_hash}{log.timestamp.isoformat()}{log.action}{json.dumps(log.detail, sort_keys=True)}"
    log.previous_hash = previous_hash
    log.current_hash = hashlib.sha256(raw.encode()).hexdigest()
    
    session.add(log)
    await session.commit()
    return log
```

### 11.4 数据备份与灾备

```yaml
# docker-compose 备份服务
backup_strategy:
  postgres:
    schedule: "0 2 * * *"          # 每日凌晨2点
    command: pg_dump -Fc prd2techspec > /backup/pg/daily_$(date +%Y%m%d).dump
    retention: 30 天
    wal_archive: 持续
    
  neo4j:
    schedule: "0 3 * * *"          # 每日凌晨3点
    command: neo4j-admin database dump neo4j --to-path=/backup/neo4j/
    retention: 14 天
    
  minio:
    schedule: "0 4 * * *"
    command: mc mirror /data/minio /backup/minio/
    retention: 90 天
    
  # 备份验证（自动恢复测试）
  verification:
    schedule: "0 8 * * 0"         # 每周日早8点
    command: |
      # 在测试环境恢复最新备份
      # 执行数据完整性检查
      # 发送验证报告
```

---

## 十二、企业级功能补充

### 12.1 协作文档

```
Collaboration Features：
┌────────────────────────────────────────────────────────────┐
│                    方案协作文档                              │
│                                                            │
│  ┌──────────────────────────────────────────────────┐      │
│  │ 文档内容区域                                      │      │
│  │                                                  │      │
│  │ # 3.1 用户服务设计                               │      │
│  │ 用户服务负责... [评论图标 3]                     │      │
│  │                                                  │      │
│  │ ┌─── 评论 (3) ───────────────────────────────┐  │      │
│  │ │ 李工: 建议增加密码重置流程设计 [回复]       │  │      │
│  │ │ 张工: 同意，已补充在第3.1.4节 [回复]       │  │      │
│  │ │ 王工: 是否考虑OAuth2集成？ [+1] [回复]     │  │      │
│  │ └─────────────────────────────────────────────┘  │      │
│  └──────────────────────────────────────────────────┘      │
│                                                            │
│  工具栏：                                                   │
│  [💬 评论] [✏️ 建议修改] [✅ 审批] [📤 分享] [📋 历史]       │
└────────────────────────────────────────────────────────────┘
```

```python
class CollaborationService:
    """协作服务 - 评论、审批、变更历史"""
    
    async def add_comment(self, doc_id: str, user_id: str,
                          section_id: str, content: str,
                          parent_comment_id: str = None) -> Comment:
        """添加评论"""
        comment = Comment(
            doc_id=doc_id, user_id=user_id,
            section_id=section_id, content=content,
            parent_comment_id=parent_comment_id,
        )
        # 通知被@的用户
        mentioned = self.extract_mentions(content)
        await self.notification_service.notify_mentions(mentioned, comment)
        return comment
    
    async def suggest_edit(self, doc_id: str, user_id: str,
                           section_id: str, original: str,
                           suggestion: str, reason: str) -> Suggestion:
        """建议修改模式"""
        suggestion = Suggestion(
            doc_id=doc_id, user_id=user_id,
            section_id=section_id,
            original=original, suggested=suggestion,
            reason=reason, status="pending",
        )
        await self.notification_service.notify_doc_owner(doc_id, suggestion)
        return suggestion
    
    async def get_change_history(self, doc_id: str) -> list[Change]:
        """获取变更历史"""
        return await self.db.query(Change).filter(
            Change.doc_id == doc_id
        ).order_by(Change.created_at.desc()).limit(100).all()
```

### 12.2 集成生态

```python
class IntegrationHub:
    """
    集成生态 - 支持多种外部系统对接
    """
    
    INTEGRATIONS = {
        "jira": JiraIntegration,
        "confluence": ConfluenceIntegration,
        "github": GitHubIntegration,
        "gitlab": GitLabIntegration,
        "feishu": FeishuIntegration,
        "dingtalk": DingtalkIntegration,
        "wecom": WecomIntegration,
        "slack": SlackIntegration,
        "webhook": WebhookIntegration,
    }
    
    async def sync_to_jira(self, task_id: str, 
                           planning_result: PlanningResult) -> dict:
        """方案 → Jira Epic/Story"""
        jira = self.get_integration("jira")
        epic = await jira.create_epic(
            project=self.get_jira_project(task_id),
            summary=f"{planning_result.project_name} - 技术方案实施",
            description=self.generate_jira_description(planning_result),
        )
        # 为每个组件创建Story
        stories = []
        for comp in planning_result.components:
            story = await jira.create_story(
                epic_id=epic["id"],
                summary=f"{comp.name}: {comp.responsibility}",
                description=self.component_to_jira_desc(comp),
                labels=[comp.type],
            )
            stories.append(story)
        return {"epic": epic, "stories": stories}
    
    async def notify_channel(self, event: str, data: dict):
        """多渠道通知"""
        # 支持 Webhook / 飞书 / 钉钉 / Slack
        webhook_urls = await self.get_webhook_urls(event)
        for url in webhook_urls:
            await self.post_webhook(url, data)
    
    async def handle_webhook(self, payload: dict):
        """自定义 Webhook 处理"""
        # 用户可配置：方案生成完成 → 调用指定URL
        # 评审通过 → 通知特定系统
        # 等
        pass
```

### 12.3 批量处理与定时任务

```python
class BatchOperations:
    """
    批量处理与定时任务
    """
    
    async def batch_import_prds(self, files: list[UploadFile]) -> list[str]:
        """批量导入 PRD"""
        task_ids = []
        for file in files:
            content = await file.read()
            task = await self.orchestrator.start_generation(
                prd_raw=content.decode(),
                prd_file_type=file.filename.split(".")[-1],
            )
            task_ids.append(task.task_id)
        return task_ids
    
    @celery.task
    def scheduled_review():
        """每周自动评审已有方案（检查是否需要更新）"""
        recent_schemes = get_recent_schemes(days=90)
        for scheme in recent_schemes:
            # 检查该方案相关的 PRD 是否有更新
            if has_prd_update(scheme.prd_id):
                # 自动重新生成方案
                trigger_regeneration(scheme.id)
    
    @celery.task
    def batch_refresh_on_tech_update(tech_name: str, new_version: str):
        """技术栈更新后批量刷新相关方案"""
        affected_schemes = find_schemes_using_tech(tech_name)
        for scheme in affected_schemes:
            # 标记为"技术栈已更新，建议重新评估"
            mark_for_review(scheme.id, f"{tech_name} 已升级到 {new_version}")
```

### 12.4 ⭐⭐ 会话历史管理

#### 12.4.1 功能概述

用户与系统的每次交互（方案生成、知识查询、评审等）都记录为一个会话。会话历史管理提供完整的查看、搜索、导出、归档能力。

```
会话生命周期：
                         ┌──────────────────┐
                         │   用户发起交互     │
                         └────────┬─────────┘
                                  │
                          ┌───────▼────────┐
                          │  创建会话       │
                          │  (LLM自动命名   │
                          │   或用户手动命名)│
                          └───────┬────────┘
                                  │
                     ┌────────────┼────────────┐
                     │            │            │
              ┌──────▼─────┐ ┌───▼────┐ ┌───▼──────┐
              │ 方案生成会话 │ │知识查询 │ │人工审核   │
              │ generate   │ │ 会话   │ │ 会话     │
              └──────┬─────┘ └───┬────┘ └───┬──────┘
                     │            │            │
                     └────────────┼────────────┘
                                  │
                          ┌───────▼────────┐
                          │  会话进行中      │
                          │  (消息逐条追加)   │
                          └───────┬────────┘
                                  │
                     ┌────────────┼────────────┐
                     │            │            │
              ┌──────▼─────┐ ┌───▼────┐ ┌───▼──────┐
              │  active    │ │archived│ │ deleted   │
              │  (进行中)   │ │(归档)   │ │(软删除)   │
              └────────────┘ └────────┘ └──────────┘
```

#### 12.4.2 会话列表与搜索

```python
class SessionHistoryService:
    """
    会话历史服务 - 列表、搜索、导出、清理
    """
    
    async def list_sessions(
        self, workspace_id: str, user_id: str,
        page: int = 1, page_size: int = 20,
        status: str = None, session_type: str = None,
        q: str = None, tags: list[str] = None,
        sort_by: str = "last_message_at",
        sort_order: str = "desc",
        date_from: str = None, date_to: str = None,
    ) -> PageResult[Session]:
        """
        会话列表 - 支持多维度筛选和排序
        
        筛选维度：
        - status: active / archived / deleted
        - session_type: generate / review / knowledge_query / chat
        - q: 搜索会话标题和摘要
        - tags: 标签过滤（数组包含）
        - date_from / date_to: 时间范围
        - sort_by: created_at / updated_at / last_message_at / title
        """
        query = self._build_base_query(workspace_id, user_id)
        
        # 状态筛选
        if status:
            query = query.filter(Session.status == status)
        
        # 类型筛选
        if session_type:
            query = query.filter(Session.session_type == session_type)
        
        # 关键词搜索（标题 + 摘要 FTS）
        if q:
            tsquery = func.plainto_tsquery('simple', q)
            query = query.filter(
                Session.title_tsv.op('@@')(tsquery) |
                Session.summary_tsv.op('@@')(tsquery)
            )
        
        # 标签筛选（数组包含）
        if tags:
            query = query.filter(Session.tags.contains(tags))
        
        # 时间范围
        if date_from:
            query = query.filter(Session.created_at >= date_from)
        if date_to:
            query = query.filter(Session.created_at <= date_to)
        
        # 排序
        sort_col = getattr(Session, sort_by, Session.last_message_at)
        order_fn = desc if sort_order == "desc" else asc
        query = query.order_by(order_fn(sort_col))
        
        # 分页
        total = await self.db.count(query)
        items = await query.offset((page - 1) * page_size).limit(page_size).all()
        
        return PageResult(items=items, total=total, page=page, page_size=page_size)
    
    async def search_messages(
        self, workspace_id: str, query: str,
        session_types: list[str] = None,
        date_from: str = None, date_to: str = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        """
        全文搜索会话消息内容
        
        搜索策略：
        1. 主搜索：PostgreSQL FTS (to_tsvector) 匹配消息内容
        2. 上下文：返回匹配消息前后各 1 条消息作为上下文
        3. 高亮：用 ts_headline 标记匹配关键词
        4. 排序：按 ts_rank 相关性排序
        """
        tsquery = func.plainto_tsquery('simple', query)
        
        # 跨会话搜索消息
        stmt = text("""
            SELECT 
                sm.id, sm.session_id, sm.role, sm.content,
                s.title as session_title, s.session_type,
                ts_rank(to_tsvector('simple', sm.content), :query) as rank,
                ts_headline('simple', sm.content, :query,
                    'StartSel=<mark>, StopSel=</mark>,
                     MaxWords=50, MinWords=20') as highlighted
            FROM session_messages sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.workspace_id = :workspace_id
              AND s.status = 'active'
              AND to_tsvector('simple', sm.content) @@ :query
              AND (:session_types IS NULL OR s.session_type = ANY(:session_types))
              AND (:date_from IS NULL OR sm.created_at >= :date_from)
              AND (:date_to IS NULL OR sm.created_at <= :date_to)
            ORDER BY rank DESC
            LIMIT :limit
        """)
        
        results = await self.db.execute(stmt, {
            "query": tsquery,
            "workspace_id": workspace_id,
            "session_types": session_types,
            "date_from": date_from,
            "date_to": date_to,
            "limit": top_k,
        })
        
        return [SearchResult(**row) for row in results]
```

#### 12.4.3 会话摘要与自动命名

```python
class SessionSummarizer:
    """
    LLM 自动生成会话摘要和标题
    
    触发时机：
    1. 会话创建时：根据首条消息生成标题
    2. 会话结束时：生成完整摘要
    3. 用户手动触发重新生成
    """
    
    TITLE_PROMPT = """
    根据以下用户请求，生成一个简洁的会话标题（20字以内）：
    
    请求内容：{first_message}
    会话类型：{session_type}
    
    输出 JSON：{{"title": "订单服务技术方案讨论"}}
    """
    
    SUMMARY_PROMPT = """
    根据以下会话历史，生成一个结构化摘要。
    
    会话标题：{title}
    会话类型：{session_type}
    
    消息内容：
    {messages}
    
    请生成摘要，包含：
    1. 会话目的（一句话）
    2. 关键结论（3-5条要点）
    3. 涉及的主要技术/组件
    4. 未解决的问题（如果有）
    5. 建议后续动作
    
    输出 JSON：
    {{
        "purpose": "讨论订单服务的技术方案选型",
        "key_conclusions": [
            "确定使用 Spring Boot 3.2 + PostgreSQL",
            "消息队列选型从 RabbitMQ 改为 RocketMQ"
        ],
        "tech_involved": ["Spring Boot", "PostgreSQL", "RocketMQ"],
        "open_issues": ["分布式事务方案待确认"],
        "suggested_actions": ["安排分布式事务专题讨论"]
    }}
    """
    
    async def generate_title(self, first_message: str, 
                              session_type: str) -> str:
        """根据首条消息生成标题"""
        result = await self.llm.complete(
            self.TITLE_PROMPT.format(
                first_message=first_message[:500],
                session_type=session_type,
            ),
            response_format={"type": "json_object"}
        )
        return json.loads(result.text)["title"]
    
    async def generate_summary(self, session: Session,
                                messages: list[SessionMessage]) -> dict:
        """生成会话摘要"""
        # 取关键消息（跳过工具调用和系统消息）
        key_messages = [
            m for m in messages[-20:]  # 最多取最近20条
            if m.role in ("user", "assistant")
        ]
        msg_text = "\n".join([
            f"[{m.role}] {m.content[:500]}"
            for m in key_messages
        ])
        
        result = await self.llm.complete(
            self.SUMMARY_PROMPT.format(
                title=session.title,
                session_type=session.session_type,
                messages=msg_text,
            ),
            response_format={"type": "json_object"}
        )
        return json.loads(result.text)
```

#### 12.4.4 会话导出

```python
class SessionExporter:
    """会话导出 - 支持 Markdown / JSON / PDF"""
    
    async def export_markdown(self, session: Session,
                               messages: list[SessionMessage]) -> str:
        """导出为 Markdown 格式（含对话树结构）"""
        lines = [
            f"# {session.title}",
            f"",
            f"- **会话类型**: {session.session_type}",
            f"- **创建时间**: {session.created_at}",
            f"- **消息数**: {session.message_count}",
            f"- **标签**: {', '.join(session.tags) if session.tags else '无'}",
            f"",
            f"---",
            f"",
        ]
        if session.summary:
            lines.extend([
                "## 会话摘要",
                session.summary,
                "",
                "---",
                "",
            ])
        
        for msg in messages:
            role_label = {"user": "👤 用户", "assistant": "🤖 助手",
                         "system": "⚙️ 系统", "tool": "🔧 工具"}
            lines.append(f"### {role_label.get(msg.role, msg.role)}")
            lines.append(f"*{msg.created_at}*")
            lines.append("")
            lines.append(msg.content)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    async def export_json(self, session: Session,
                           messages: list[SessionMessage]) -> dict:
        """导出为 JSON 格式（机器可读）"""
        return {
            "session": session.dict(),
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "content_type": m.content_type,
                    "attachments": m.attachments,
                    "created_at": m.created_at.isoformat(),
                    "token_count": m.token_count,
                    "model_used": m.model_used,
                    "latency_ms": m.latency_ms,
                }
                for m in messages
            ],
            "exported_at": datetime.utcnow().isoformat(),
        }
    
    async def export_pdf(self, session: Session,
                          messages: list[SessionMessage]) -> bytes:
        """导出为 PDF（Markdown → HTML → WeasyPrint）"""
        md_content = await self.export_markdown(session, messages)
        html = markdown_to_html(md_content)
        return weasyprint.HTML(string=html).write_pdf()
```

#### 12.4.5 会话老化与清理策略

```python
class SessionCleanupPolicy:
    """
    会话老化清理策略
    
    策略矩阵：
    ┌──────────────┬──────────────┬──────────────┬──────────────┐
    │ 计划等级     │ active 保留   │ archive 保留  │ 删除条件      │
    ├──────────────┼──────────────┼──────────────┼──────────────┤
    │ Free         │ 30天         │ 90天         │ 手动或超期   │
    │ Pro          │ 180天        │ 365天        │ 手动          │
    │ Enterprise   │ 不限         │ 不限         │ 仅手动       │
    └──────────────┴──────────────┴──────────────┴──────────────┘
    """
    
    async def apply_cleanup_policy(self, workspace_id: str):
        """执行清理策略"""
        workspace = await self.get_workspace(workspace_id)
        plan = workspace.plan  # free / pro / enterprise
        
        if plan == "free":
            # active 超过30天的自动归档
            cutoff = datetime.utcnow() - timedelta(days=30)
            await self._auto_archive(cutoff)
            
            # archived 超过90天的删除
            delete_cutoff = datetime.utcnow() - timedelta(days=90)
            await self._auto_delete(delete_cutoff)
        
        elif plan == "pro":
            # active 超过180天的自动归档
            cutoff = datetime.utcnow() - timedelta(days=180)
            await self._auto_archive(cutoff)
            
            # archived 超过365天的标记过期
            expire_cutoff = datetime.utcnow() - timedelta(days=365)
            await self._mark_expired(expire_cutoff)
        
        # enterprise 不做自动清理
```

### 12.5 ⭐⭐ 已上传文档管理

#### 12.5.1 功能概述

统一管理用户上传到系统的所有文档，包括文档上传、预览、搜索、去重、批量操作、生命周期管理。

```
文档管理功能全景：
┌─────────────────────────────────────────────────────────────────────────┐
│                         文档管理                                        │
│                                                                          │
│  上传 ─────→ 处理 ─────→ 索引 ─────→ 管理 ─────→ 删除                    │
│   │           │            │           │           │                     │
│   ├─ 单文件   ├─ 格式检测  ├─ 分块    ├─ 列表     ├─ 软删除              │
│   ├─ 批量     ├─ 文本提取  ├─ 实体    ├─ 搜索     │                     │
│   ├─ Web导入  ├─ 预览生成  ├─ 向量    ├─ 预览     │                     │
│   └─ API导入  └─ 去重     └─ 图谱    └─ 重索引   └─ 永久删除            │
│                                                                          │
│  存储架构：                                                              │
│  ┌──────────────────────────────────────────────────────────┐           │
│  │  PostgreSQL (元数据)     MinIO (文件实体)                 │           │
│  │  ┌──────────────────┐   ┌───────────────────┐           │           │
│  │  │ uploaded_documents│   │ bucket: prd-docs  │           │           │
│  │  │ - 文件名/类型/大小│   │  /{workspace_id}/ │           │           │
│  │  │ - 处理状态        │   │   {yyyy}/{mm}/    │           │           │
│  │  │ - 提取统计        │   │   {file_hash}.ext │           │           │
│  │  │ - FTS索引         │   └───────────────────┘           │           │
│  │  └──────────────────┘                                   │           │
│  └──────────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 12.5.2 文档上传与处理流水线

```python
class DocumentUploadService:
    """
    文档上传与处理 - 异步流水线
    上传即触发后台处理，不阻塞用户
    """
    
    UPLOAD_CONFIG = {
        "max_file_size": 50 * 1024 * 1024,  # 50MB
        "allowed_types": {
            "md":   {"mime": "text/markdown",          "processors": ["text_extract", "chunk", "index"]},
            "pdf":  {"mime": "application/pdf",         "processors": ["pdf_extract", "chunk", "index"]},
            "docx": {"mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                                                         "processors": ["docx_extract", "chunk", "index"]},
            "txt":  {"mime": "text/plain",              "processors": ["text_extract", "chunk", "index"]},
            "csv":  {"mime": "text/csv",                "processors": ["csv_parse", "dual_index"]},
            "tsv":  {"mime": "text/tab-separated-values","processors": ["csv_parse", "dual_index"]},
            "png":  {"mime": "image/png",               "processors": ["vision_extract", "clip_embed"]},
            "jpg":  {"mime": "image/jpeg",              "processors": ["vision_extract", "clip_embed"]},
            "jpeg": {"mime": "image/jpeg",              "processors": ["vision_extract", "clip_embed"]},
        },
    }
    
    async def upload(self, file: UploadFile, workspace_id: str,
                     user_id: str, session_id: str = None,
                     tags: list[str] = None) -> UploadedDocument:
        """
        上传文档完整流程：
        
        1. 文件校验（大小、类型、病毒扫描）
        2. SHA-256 哈希计算（去重检测）
        3. 存储到 MinIO（按日期分桶）
        4. 元数据写入 PostgreSQL
        5. 触发异步处理任务（Celery）
        6. 返回文档记录
        """
        # Step 1: 文件校验
        content = await file.read()
        if len(content) > self.UPLOAD_CONFIG["max_file_size"]:
            raise FileTooLargeError(f"文件大小超过限制 50MB")
        
        ext = file.filename.split(".")[-1].lower()
        if ext not in self.UPLOAD_CONFIG["allowed_types"]:
            raise UnsupportedFileTypeError(f"不支持的文件类型: .{ext}")
        
        # Step 2: 去重检测
        file_hash = hashlib.sha256(content).hexdigest()
        existing = await self._find_duplicate(workspace_id, file_hash)
        if existing:
            # 已有相同文件，返回已有记录（可配置是否允许重复上传）
            return existing
        
        # Step 3: 存储到 MinIO
        storage_path = self._build_storage_path(workspace_id, file_hash, ext)
        await self.object_store.put(storage_path, content)
        
        # Step 4: 元数据写入
        doc = UploadedDocument(
            workspace_id=workspace_id,
            user_id=user_id,
            original_filename=file.filename,
            storage_path=storage_path,
            file_size=len(content),
            file_type=ext,
            mime_type=self.UPLOAD_CONFIG["allowed_types"][ext]["mime"],
            file_hash=file_hash,
            session_id=session_id,
            tags=tags or [],
            processing_status="pending",
        )
        self.db.add(doc)
        await self.db.commit()
        
        # Step 5: 触发异步处理
        process_document_task.delay(doc.id)
        
        return doc
    
    def _build_storage_path(self, workspace_id: str,
                             file_hash: str, ext: str) -> str:
        """
        MinIO 存储路径规则：
        prd-docs/{workspace_id}/{yyyy}/{mm}/{file_hash}.{ext}
        
        按日期分桶便于生命周期管理（冷热数据分层）
        """
        now = datetime.utcnow()
        return (
            f"prd-docs/{workspace_id}/"
            f"{now.year}/{now.month:02d}/"
            f"{file_hash}.{ext}"
        )


@celery.task(bind=True, max_retries=3)
def process_document_task(self, doc_id: str):
    """
    文档处理任务 - 异步执行
    
    处理流水线（按文件类型不同）：
    
    叙事文档 (.md/.pdf/.docx/.txt):
      → 文本提取 (Unstructured/Docling)
      → 文档预览生成（前几页Markdown）
      → 多粒度分块 (Sentence/Paragraph/Section)
      → 实体提取 → 关系提取
      → TextUnit 构建 → Embedding
      → 写入知识图谱 (Neo4j + PGVector)
      → 更新处理状态
    
    CSV/TSV:
      → CSV 解析 (pandas)
      → 列分析 → 列级 Embedding
      → 行级 TextUnit 构建
      → 外键检测
      → 双通路索引 (行级+列级)
      → 更新处理状态
    
    图片 (.png/.jpg):
      → 缩略图生成
      → GPT-4o 视觉提取（组件+关系）
      → CLIP 双向量编码 (visual_emb + text_emb)
      → ImageChunk 构建 → 写入 PGVector
      → 更新处理状态
    """
    try:
        service = DocumentProcessingService()
        doc = service.get_document(doc_id)
        service.update_status(doc_id, "processing")
        
        # 按类型执行处理流水线
        if doc.file_type in ("md", "pdf", "docx", "txt"):
            result = service.process_narrative_document(doc)
        elif doc.file_type in ("csv", "tsv"):
            result = service.process_tabular_document(doc)
        elif doc.file_type in ("png", "jpg", "jpeg"):
            result = service.process_image_document(doc)
        
        # 更新提取统计
        service.update_document_stats(doc_id, result)
        service.update_status(doc_id, "indexed")
        
    except Exception as e:
        get_task().update_state(state="FAILURE")
        service.update_status(doc_id, "failed", error=str(e))
        raise self.retry(exc=e, countdown=60)
```

#### 12.5.3 文档预览系统

```python
class DocumentPreviewService:
    """
    文档预览生成 - 支持多种文件类型的预览
    
    预览策略：
    ┌──────────┬──────────────────────────────────────────────────────┐
    │ 文件类型  │ 预览方式                                            │
    ├──────────┼──────────────────────────────────────────────────────┤
    │ .md      │ 直接渲染 Markdown → HTML                            │
    │ .pdf     │ 提取前3页文本 + 第一页缩略图                         │
    │ .docx    │ 提取前2000字 + 标题结构树                            │
    │ .csv/.tsv│ 前20行表格渲染 + 列统计摘要                          │
    │ .png/.jpg│ 缩略图 + OCR 文字提取（如有）                        │
    │ .txt     │ 前2000字预览                                         │
    └──────────┴──────────────────────────────────────────────────────┘
    """
    
    async def generate_preview(self, doc: UploadedDocument) -> dict:
        """生成文档预览"""
        preview = {"type": doc.file_type, "data": None}
        
        if doc.file_type == "md":
            # Markdown → HTML 渲染
            raw = await self.object_store.get(doc.storage_path)
            html = markdown.markdown(raw.decode())
            preview["data"] = {"html": html, "word_count": len(raw)}
        
        elif doc.file_type == "pdf":
            # PDF 预览
            raw = await self.object_store.get(doc.storage_path)
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(raw)
                tmp.flush()
                
                # 提取文本
                text = extract_text_from_pdf(tmp.name, max_pages=3)
                # 生成缩略图（第一页）
                thumbnail = self._pdf_thumbnail(tmp.name)
                
                preview["data"] = {
                    "text_preview": text[:2000],
                    "thumbnail_base64": thumbnail,
                    "page_count": doc.page_count,
                }
        
        elif doc.file_type in ("csv", "tsv"):
            # CSV 表格预览
            raw = await self.object_store.get(doc.storage_path)
            import io
            import pandas as pd
            df = pd.read_csv(io.BytesIO(raw), nrows=20)
            
            preview["data"] = {
                "headers": df.columns.tolist(),
                "rows": df.head(20).values.tolist(),
                "total_rows": doc.word_count or len(df),
                "columns_preview": [
                    {"name": col, "dtype": str(df[col].dtype),
                     "sample": df[col].dropna().head(3).tolist()}
                    for col in df.columns
                ],
            }
        
        elif doc.file_type in ("png", "jpg", "jpeg"):
            # 图片预览
            raw = await self.object_store.get(doc.storage_path)
            import base64
            preview["data"] = {
                "image_base64": base64.b64encode(raw).decode(),
                "mime_type": doc.mime_type,
            }
        
        return preview
```

#### 12.5.4 文档搜索（混合搜索）

```python
class DocumentSearchService:
    """
    文档搜索 - 三级搜索策略
    
    搜索策略路由：
    
    用户查询
      │
      ├── 文件名精确匹配（最高优先级）
      │   → "订单服务设计文档.pdf" 精确搜索文件名
      │
      ├── 全文检索（PostgreSQL FTS）
      │   → 搜索标题 + 描述 + 提取的文本内容
      │   → to_tsvector('simple', title || ' ' || description)
      │   → 按 ts_rank 排序
      │
      └── 语义检索（PGVector，可选）
          → 如果文档内容已向量化
          → 用查询向量匹配文档 embedding
          → 与 FTS 结果 RRF 融合
    """
    
    async def search(self, workspace_id: str, query: str,
                     file_type: str = None,
                     use_semantic: bool = False,
                     top_k: int = 20) -> list[ScoredDoc]:
        """混合搜索入口"""
        
        # 路1: FTS 全文检索
        fts_results = await self._fts_search(
            workspace_id, query, file_type, top_k
        )
        
        if not use_semantic:
            return fts_results
        
        # 路2: 语义检索
        semantic_results = await self._semantic_search(
            workspace_id, query, file_type, top_k
        )
        
        # RRF 融合
        return self._rrf_fusion(fts_results, semantic_results)[:top_k]
    
    async def _fts_search(self, workspace_id: str, query: str,
                           file_type: str, top_k: int) -> list[ScoredDoc]:
        """PostgreSQL 全文检索"""
        tsquery = func.plainto_tsquery('simple', query)
        
        stmt = text("""
            SELECT 
                id, original_filename, file_type, file_size,
                title, description, processing_status,
                created_at,
                ts_rank(
                    to_tsvector('simple', 
                        coalesce(title,'') || ' ' || coalesce(description,'')),
                    :query
                ) as rank,
                ts_headline('simple',
                    coalesce(title,'') || ' ' || coalesce(description,''),
                    :query,
                    'StartSel=<mark>, StopSel=</mark>, MaxWords=30'
                ) as highlight
            FROM uploaded_documents
            WHERE workspace_id = :workspace_id
              AND is_deleted = FALSE
              AND processing_status = 'indexed'
              AND to_tsvector('simple', 
                  coalesce(title,'') || ' ' || coalesce(description,'')) @@ :query
              AND (:file_type IS NULL OR file_type = :file_type)
            ORDER BY rank DESC
            LIMIT :limit
        """)
        
        results = await self.db.execute(stmt, {
            "query": tsquery,
            "workspace_id": workspace_id,
            "file_type": file_type,
            "limit": top_k,
        })
        
        return [
            ScoredDoc(id=r.id, text=f"{r.title}: {r.description}",
                      score=r.rank, source="fts",
                      metadata={"filename": r.original_filename,
                               "file_type": r.file_type,
                               "highlight": r.highlight})
            for r in results
        ]
    
    async def _semantic_search(self, workspace_id: str, query: str,
                                file_type: str, top_k: int) -> list[ScoredDoc]:
        """语义检索 - PGVector"""
        query_emb = self.embed_model.embed(query)
        
        stmt = text("""
            SELECT id, original_filename, title, description,
                   1 - (embedding <=> :query_emb) as similarity
            FROM uploaded_documents
            WHERE workspace_id = :workspace_id
              AND is_deleted = FALSE
              AND processing_status = 'indexed'
              AND embedding IS NOT NULL
              AND (:file_type IS NULL OR file_type = :file_type)
            ORDER BY embedding <=> :query_emb
            LIMIT :limit
        """)
        
        results = await self.db.execute(stmt, {
            "query_emb": json.dumps(query_emb),
            "workspace_id": workspace_id,
            "file_type": file_type,
            "limit": top_k,
        })
        
        return [
            ScoredDoc(id=r.id, text=f"{r.title}: {r.description}",
                      score=r.similarity, source="semantic",
                      metadata={"filename": r.original_filename})
            for r in results
        ]
```

#### 12.5.5 文档统计看板

```python
class DocumentStatsService:
    """文档统计看板"""
    
    async def get_workspace_stats(self, workspace_id: str) -> dict:
        """获取工作空间文档统计"""
        
        stats = await self.db.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER(WHERE processing_status = 'indexed') as indexed_count,
                COUNT(*) FILTER(WHERE processing_status = 'pending') as pending_count,
                COUNT(*) FILTER(WHERE processing_status = 'failed') as failed_count,
                SUM(file_size) as total_size,
                COUNT(*) FILTER(WHERE created_at >= NOW() - INTERVAL '7 days') as recent_uploads,
                
                -- 按类型分布
                JSONB_OBJECT_AGG(file_type, type_count) as by_type,
                
                -- 按状态分布
                JSONB_OBJECT_AGG(processing_status, status_count) as by_status
            FROM (
                SELECT * FROM uploaded_documents 
                WHERE workspace_id = :workspace_id AND is_deleted = FALSE
            ) base
            CROSS JOIN LATERAL (
                SELECT file_type, COUNT(*) as type_count
                FROM uploaded_documents
                WHERE workspace_id = :workspace_id AND is_deleted = FALSE
                GROUP BY file_type
            ) type_stats
            CROSS JOIN LATERAL (
                SELECT processing_status, COUNT(*) as status_count
                FROM uploaded_documents
                WHERE workspace_id = :workspace_id AND is_deleted = FALSE
                GROUP BY processing_status
            ) status_stats
            GROUP BY type_stats.file_type, status_stats.processing_status
        """), {"workspace_id": workspace_id})
        
        return dict(stats.fetchone())
```

---

## 十三、CI/CD 流水线

```yaml
# .github/workflows/ci.yml
name: PRD2TechSpec CI/CD

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install -r requirements.txt
      
      - name: Lint
        run: |
          ruff check . --config pyproject.toml
          mypy . --ignore-missing-imports
      
      - name: Unit tests
        run: pytest tests/unit/ -v --cov=./ --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
  
  build-and-push:
    needs: lint-and-test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      
      - name: Build Docker images
        run: |
          docker build -t prd2techspec-api:latest -f Dockerfile .
          docker build -t prd2techspec-celery:latest -f Dockerfile.celery .
      
      - name: Push to registry
        run: |
          docker tag prd2techspec-api:latest ${{ secrets.REGISTRY }}/prd2techspec-api:${{ github.sha }}
          docker push ${{ secrets.REGISTRY }}/prd2techspec-api:${{ github.sha }}

  deploy-staging:
    needs: build-and-push
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy to staging
        run: |
          # 使用 docker-compose 或 k8s 部署到测试环境
          ssh ${{ secrets.STAGING_HOST }} "cd /app && docker-compose pull && docker-compose up -d"
  
  knowledge-sync:
    runs-on: ubuntu-latest
    schedule:
      - cron: '0 6 * * 1'  # 每周一早6点
    steps:
      - name: Run knowledge base sync
        run: python scripts/init_knowledge.py --sync
```

---

## 十四、技术栈总结

| 层级 | 组件 | 选型 | 版本建议 |
|------|------|------|---------|
| **Agent 框架** | LangGraph | `langgraph>=0.2.0` | 状态图驱动 |
| **Graph RAG** | LlamaIndex | `llama-index>=0.11.0` | PropertyGraphIndex |
| **图数据库** | Neo4j | 5.x | APOC + GDS 插件 |
| **向量存储** | PGVector | pgvector 0.7+ | PostgreSQL 16 插件 |
| **全文检索** | PostgreSQL FTS | 内置 | tsvector |
| **重排模型** | BAAI/bge-reranker-v2-m3 | 568M | 可换成 Gemma 2B |
| **Embedding** | BAAI/bge-large-zh-v1.5 | 1024维 | 中文最佳开源 |
| **⭐ 多模态模型** | openai/clip-vit-large-patch14 | 768维 | CLIP 双塔: visual+text 同一空间，支持以图搜图 |
| **⭐ 多模态 LLM** | GPT-4o / Claude Opus 4 | - | 图片理解(管道A)，架构图生成(管道B) |
| **⭐ 图表渲染** | mermaid-cli (mmdc) / Kroki | latest | Mermaid→PNG/SVG 渲染引擎 |
| **文档解析** | Unstructured + Docling | latest | PDF/DOCX/图片 |
| **⭐ CSV 解析** | pandas + chardet | latest | CSV/TSV 加载+编码检测+列类型推断 |
| **⭐ Web 抓取** | requests + BeautifulSoup4 + readability-lxml | latest | HTTP 抓取+HTML 解析+正文提取 |
| **⭐ 爬虫框架** | asyncio + aiohttp (可选 Scrapy) | latest | 同域递归爬取+并发控制+robots.txt |
| **⭐ 定时调度** | croniter + Celery Beat | latest | Cron 表达式解析+定时同步任务 |
| **LLM 主模型** | DeepSeek-V3 / GPT-4o | - | 中文场景 DeepSeek 性价比高 |
| **LLM Judge** | GPT-4o-mini / DeepSeek | - | 低成本评测 |
| **API 框架** | FastAPI | 0.110+ | 异步原生 |
| **任务队列** | Celery + Redis | Celery 5.4+ | 长耗时任务 |
| **对象存储** | MinIO | latest | 文档存储 |
| **配置管理** | pydantic-settings | 2.x | 环境变量驱动 |
| **前端（可选）** | Streamlit | 1.35+ | 快速搭建 |
| **监控** | Prometheus + Grafana | latest | 指标 + 面板 |
| **容器化** | Docker Compose | 3.8+ | 本地部署 |
| **SSO/身份认证** | Keycloak | 24.x | OIDC/SAML 协议 |
| **LLM 可观测** | LangFuse / LangSmith | latest | 每次LLM调用的完整trace |
| **分布式追踪** | OpenTelemetry + Jaeger | latest | 全链路追踪 |
| **代码生成** | python-docx-template | latest | DOCX 模板导出 |
| **PDF导出** | WeasyPrint / Pandoc | latest | Markdown→PDF |
| **协作文档** | 自建 (WebSocket) | - | 评论+建议修改 |
| **Webhook** | 自建 | - | 自定义事件回调 |
| **国际化(i18n)** | Babel + self-built | latest | 多语言PRD支持 |

---

## 十五、实施路线图（完整版）

### 15.1 分阶段计划

| 阶段 | 内容 | 新增内容 | 预计工作量 | 产出 |
|------|------|---------|-----------|------|
| **Phase 1** (3周) | 基础设施 + 多租户 + 权限 + Knowledge Layer 基础 | Auth模块 + RBAC + Keycloak集成 | 20人天 | 可多用户使用的知识库 |
| **Phase 2** (1周) | Knowledge Layer 多路检索 + 重排 + 生命周期管理 | 实体融合/多模态/老化/版本控制 | 10人天 | 完整 RAG 流水线 |
| **Phase 2.5** (0.5周) | ⭐⭐ CSV + Web URL 扩展（新增） | CSVLoader/WebLoader/爬虫/定时同步 | 5人天 | 多格式输入就绪 |
| **Phase 3** (2周) | Analysis Layer + 增强节点 | 语言检测/质量评分/工作量估算/干系人 | 14人天 | 文档分析 Agent |
| **Phase 4** (3周) | Planning Layer + 增强节点 | 成本估算/时间线/技能缺口/风险量化 | 16人天 | 架构规划 Agent |
| **Phase 5** (3周) | Generation Layer + 模板系统 + 多格式导出 | 3级模板/PDF/DOCX/Confluence/Notion导出 | 16人天 | 方案生成 Agent |
| **Phase 6** (2周) | Evaluation(10维) + 评分校准 | 5个新增维度/平行评测/反馈闭环 | 12人天 | 完整评测体系 |
| **Phase 7** (2周) | Orchestrator + LLM Gateway + 观测性 | 模型路由/成本追踪/OpenTelemetry/告警 | 12人天 | 全链路串联+可观测 |
| **Phase 8** (3周) | 协作文档 + 集成生态 + 数据安全 | 评论/建议修改/Jira/飞书/Webhook/安全审计 | 16人天 | 企业级功能就绪 |
| **Phase 8.5** (1.5周) | ⭐⭐ 会话历史 + 文档管理（新增） | 会话列表/搜索/导出/老化 + 文档上传/预览/去重/混合搜索 | 8人天 | 历史回看和文档管理就绪 |
| **Phase 9** (1周) | CI/CD + 多环境部署 + 文档 | GitHub Actions/灾备/部署文档/用户指南 | 8人天 | 生产就绪 |
| **Phase 10** (持续) | 反馈闭环 + 知识图谱增强 + 迭代优化 | 用户反馈→评分校准→系统进化 | 2人天/周 | 系统持续进化 |

### 15.2 团队配置建议

```
Phase 1-2 (基础设施):    2人（后端+基础设施）
Phase 3-4 (核心Agent):   3人（2后端+1AI工程师）
Phase 5-6 (生成+评测):   3人（2后端+1AI工程师）
Phase 7-8.5 (企业级功能): 3人（2后端+1前端）
Phase 9 (上线):          3人全部
Phase 10 (持续):         1-2人维护
```

### 15.3 关键里程碑

```
M1 (Week 3):  ✅ 多租户知识图谱可用
M2 (Week 6):  ✅ PRD分析Agent完成
M3 (Week 9):  ✅ 架构规划Agent完成
M4 (Week 12): ✅ 方案生成+评测完成
M5 (Week 14): ✅ 全链路可观测上线
M6 (Week 17): ✅ 企业级功能交付
M7 (Week 19): ✅ 会话历史+文档管理交付
M8 (Week 20): ✅ 生产环境就绪
```

**总计约 137 人天**（含 CSV+Web URL 扩展 5 人天 + 会话历史与文档管理 8 人天），推荐 3 名工程师（2后端+1 AI），约 **4.7个月** 完成完整版。

### 15.4 快速启动建议

如团队资源有限，可按以下优先级分期交付：

| 优先级 | 必须功能 | 建议分期 |
|--------|---------|---------|
| **P0** | 多租户+RBAC / Knowledge Layer检索 / Analysis Layer | Phase 1-3 |
| **P1** | Planning Layer / Generation Layer / Evaluation | Phase 4-6 |
| **P2** | ⭐⭐ CSV 索引 / 单次 Web URL 索引 / LLM Gateway / 多格式导出 / 模板系统 | Phase 7 前半 |
| **P3** | ⭐⭐ Web 爬虫+定时同步 / 观测性 / 协作 / 集成 / 安全审计 | Phase 7 后半 + Phase 8 |
| **P4** | ⭐⭐ 会话历史管理 + 已上传文档管理（新增） | Phase 8.5 |

P0+P1 约 **60人天**，3人 **2个月** 可交付核心可用版本。
P2（CSV+单次URL索引）约 **+6人天**，P3（爬虫+定时同步+协作+集成）约 **+26人天**，P4（会话历史+文档管理）约 **+8人天**。

### 15.5 Vibe Coding 模式估算

> **Vibe Coding** 模式：AI 负责所有代码生成，人只做 Prompt 投喂 + 输出 Review + 集成调试。
> 前提：已有完整 Tech Spec（本文档），使用 Claude Code / Cursor Agent 级别工具。

#### 按轮次估算（人只把控细节）

| 模块 | 轮次 | 每轮(min) | PD | 说明 |
|------|------|----------|-----|------|
| 项目脚手架 + Docker + CI/CD | 3-5 | 15 | **0.3** | 一次性生成，基本不改 |
| 所有数据模型 + SQL | 2-3 | 15 | **0.2** | 声明式，AI一把出 |
| 4层 Agent Graph 定义 | 4-6 | 20 | **0.5** | 结构固定，一次成型 |
| ~20个 Node Prompt + 模型 | 5-8 | 20 | **0.7** | prompt工程主要在这 |
| 知识图谱 Pipeline | 3-5 | 20 | **0.5** | 需调试连接 |
| ⭐⭐ CSV 加载+索引 | 2-3 | 15 | **0.2** | pandas 方案成熟 |
| ⭐⭐ Web Loader+爬虫+定时同步 | 4-6 | 20 | **0.5** | 爬虫调试+robots.txt |
| 模板系统 + 导出 | 3-4 | 15 | **0.3** | 依赖库 adapter 调试 |
| Auth + 多租户 | 3-5 | 20 | **0.5** | 安全逻辑需多轮确认 |
| 集成 (Jira/飞书等×6) | 6-10 | 15 | **0.7** | 每个集成分开搞 |
| API Routes全部 | 3-5 | 15 | **0.3** | CRUD一把梭 |
| 评测10维 + 校准 | 4-6 | 20 | **0.5** | 评分逻辑需调 |
| **子总计（生成）** | **42-68** | - | **~5.2** | 新增约 0.7 PD |
| 集成测试 + 修bug | 10-15轮 | 30 | **3** | 真正耗时的在这 |
| 部署调试 | 5-8轮 | 30 | **1.5** | 环境问题无法避免 |
| 架构决策 / 方向调整 | 全程穿插 | - | **1** | 人的核心价值 |
| **Vibe Coding 总计** | | | **~10 PD** | |

#### 对比总结

| 模式 | 总PD | 人力配置 | 日历时间 | 加速比 |
|------|------|---------|---------|-------|
| **纯人工** | 137 PD | 3人 | 4.7 月 | 1x |
| **AI辅助** | 29 PD | 1人 | 1.5 月 | 4.7x |
| **+CSV+Web扩展** | +16 PD | - | - | - |
| **+会话历史+文档管理** | +8 PD | - | - | - |
| **Vibe Coding** | **~11.5 PD** | **1人** | **2-3 周** | **~12x** |

#### 推荐 2.5 周 Sprint 安排

```
Week 1 (5天): 核心代码生成 + 跑通
  Mon: 脚手架 + DB模型 + Auth + 会话/文档表     → 一次性生成
  Tue: Knowledge Layer + ⭐⭐ CSV Loader + ⭐⭐ Web Loader → prompt逐步投喂
  Wed: Planning Layer + Generation Layer        → 核心逻辑
  Thu: Evaluation + 10维评分                     → 评测体系
  Fri: 会话历史服务 + 文档管理服务 + API          → 用户界面数据

Week 2 (5天): 集成调试 + 修边界 + 补充功能
  Mon: 端到端跑通 + 修大bug + 会话列表/搜索联调
  Tue: 文档上传/预览/去重联调 + 异常流程
  Wed: 集成测试 + 多租户验证 + 权限检查
  Thu: 部署 + 文档 + 会话老化策略测试
  Fri: 回归 + 交付

Week 3 (前2天): 可选补丁
  Mon: 性能优化（会话列表分页、FTS查询）
  Tue: 最终验收 + 文档收尾
```

#### Vibe Coding 成功关键

```
必要条件：
├── 有完整 Tech Spec（本文档就是最大资产）                → ✅ 已有
├── 每次 prompt 只给一个模块，不超过 500行输出
├── 每次生成后立即跑通，不要堆代码再 debug
├── 使用 Claude Code / Cursor Agent 级别 agent
├── 接受 AI 偶尔翻车（~15%），直接重新生成而非手动改
└── 人聚焦在：架构方向 / 边界条件 / 安全 / 测试 这四个环节
```