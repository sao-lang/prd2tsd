# 块 E：企业级功能

> 关联总文档：`prd2tsd.md` §1.2 LLM Gateway、§1.3 观测性、§11 数据安全、§12 企业级功能补充（会话历史+文档管理+集成生态）
>
> **前置条件**：块 D 已完成且端到端全链路可跑通。本块在已有链路上做增量增强，不做架构改动。

---

## 1. 需求描述

在块 D 的基础上增加企业级功能：LLM 成本管控、系统观测、会话历史、文档管理、外部集成。

### 核心功能列表

**E1 — LLM Gateway（模型管理与成本控制）**
- 模型路由策略（按任务类型自动选模型）
- 成本追踪（每次 LLM 调用记录 token 消耗和费用）
- 语义缓存（相同查询命中缓存不重复调用）
- 预算控制（工作空间月预算超过 90% 自动降级到低成本模型）

**E2 — 观测性（Observability）**
- OpenTelemetry 分布式追踪（每个请求的全链路 Span）
- Prometheus 指标（LLM 调用数、成本、延迟、任务耗时）
- 告警规则（成本异常、质量评分下降、高延迟）

**E3 — 会话历史管理**
- 会话列表（分页、筛选、排序）
- 消息查看（按轮次显示对话内容）
- 会话搜索（PostgreSQL FTS 全文搜索消息内容）
- 会话导出（Markdown / JSON）
- 会话老化清理（Free 30天 / Pro 180天 / Enterprise 不限）

**E4 — 已上传文档管理**
- 文档上传（.md/.pdf/.docx/.txt/.csv/.png 等）
- SHA-256 文件去重
- 文档预览（Markdown 渲染、PDF 缩略图、CSV 前 20 行表格）
- 文档搜索（文件名 FTS + 语义向量混合搜索）
- 文档统计看板（按类型/状态分布、存储量）

**E5 — 集成生态**
- Webhook 通知（方案完成时回调指定 URL）
- 飞书/钉钉通知（可选）

**E6 — ⭐⭐ CSV 双通路索引**
- CSV/TSV 行级 TextUnit 构建（每行→自然语言句子）
- 列级 Embedding（列名+列描述→语义向量）
- 列类型自动推断（string/integer/float/enum/date）
- 外键自动检测（列名 _id/_key 后缀启发）
- 行级+列级双通路 PGVector 索引

**E7 — ⭐⭐ Web 资源索引**
- 单次 URL 抓取（Readability 正文提取→Markdown）
- 同域递归爬虫（BFS+robots.txt+并发控制）
- 定时同步（ETag/Last-Modified/内容哈希变更检测）
- 增量更新知识图谱

**E8 — ⭐⭐ CLIP 多模态/以图搜图**
- 图片上传→CLIP 视觉 Embedding（768d）
- 文本描述→CLIP 文本 Embedding（768d）
- 图文混合检索（以图搜图+文搜图+RRF 融合）
- ImageChunk 双向量存储（visual_emb + text_emb 同一空间）

**E9 — ⭐ 协作文档**
- 行内评论（选中段落→添加评论→@提及通知）
- 建议修改（原文+建议+理由→owner 审批）
- 变更历史（版本对比+回滚）

**E10 — ⭐ 批量处理与定时任务**
- Celery Beat 定时任务（知识图谱定期刷新）
- 批量文档重索引
- 批量方案重新生成（技术栈更新时触发）
- 定时同步 Web 资源

**E11 — ⭐ 搜索引擎回退**
- 本地知识图谱检索命中不足时自动触发网络搜索
- LLM 生成搜索关键词
- 结果实时索引并返回

---

## 2. 目标

| 目标 | 衡量标准 |
|------|---------|
| LLM 成本可追踪 | 每次 LLM 调用记录 model/input_tokens/output_tokens/cost |
| 链路可追踪 | 每个请求有完整 Span 链，可通过 Jaeger 查看 |
| 会话可回看 | 创建会话 → 加消息 → 列表 → 搜索 → 导出 全部可用 |
| 文档可管理 | 上传 → 去重 → 预览 → 搜索 → 删除 全部可用 |
| CSV 双通路索引 | CSV 上传后行级+列级均可检索 |
| Web 资源可索引 | URL 抓取 → 正文提取 → 知识图谱写入 |
| 以图搜图可用 | 上传图片 → 找到相似架构图 |
| 协作文档可用 | 评论/建议修改/变更历史全流程 |
| 定时任务生效 | Celery Beat 定时刷新知识图谱 |
| 搜索引擎回退 | 本地无结果时自动触发网络搜索 |
| 端到端仍然通 | 块 D 的 test_full_flow.py 仍然 PASS |

---

## 3. 使用技术栈

```yaml
# === 强制使用 ===
web: fastapi>=0.110                        # 继承块 A
test: pytest>=8.0 + pytest-asyncio
lint: ruff
type_check: mypy

# === 新增依赖 ===
new_deps:
  - opentelemetry-api                      # 分布式追踪
  - opentelemetry-sdk
  - opentelemetry-exporter-otlp
  - prometheus-client                      # 指标收集
  - minio                                  # 对象存储 SDK
  - celery                                 # 定时任务（块 E 引入）
  - redis                                  # 消息队列（块 E 引入）
  - scrapy                                 # Web 爬虫（可选，也可用 aiohttp）
  - pillow                                 # 图片处理（多模态缩略图）
  - transformers                           # CLIP 模型（多模态 Embedding）
  - httpx                                  # Webhook 发送

# === 新增容器 ===
new_services:
  - jaeger                                 # 分布式追踪
  - prometheus                             # 指标收集
  - minio                                  # 文档对象存储
  - redis                                  # Celery 消息队列

# === 仍然禁止 ===
forbidden:
  - langchain 任何包
  - chromadb / qdrant / weaviate
```

---

## 4. Coding 约束

### 增量开发原则

```
✅ 在块 D 的 app/ 目录下增加新文件，不做大规模重构
✅ 新功能通过新增 FastAPI 路由注册到 app/main.py
✅ 复用块 A 的 Auth 中间件做权限检查
✅ 复用块 B 的 document_loader / chunker（文档管理）
❌ 不修改 contracts/interfaces.py 已有的接口
❌ 不修改各 Layer 的 Node 逻辑
❌ 不修改块 D 的 Orchestrator 主流程
```

### LLM Gateway 使用规则

```python
# ✅ 正确：通过 Gateway 调用 LLM，不走裸 OpenAI
from app.llm_gateway import gateway

result = await gateway.complete(
    prompt="...",
    task_type="analysis.requirement",   # 自动路由到正确模型
    workspace_id="...",                  # 自动追踪成本
)

# ❌ 错误：直接调 LLM 客户端（跳过成本追踪和路由）
from app.core.llm import get_llm
llm = get_llm()
result = llm.complete(prompt)            # 禁止 — 无成本追踪
```

---

## 5. 数据结构

### 5.1 E1 — LLM Gateway 数据

```sql
-- llm_call_logs: 每次 LLM 调用记录
CREATE TABLE llm_call_logs (
    id UUID PK,
    task_id UUID,
    workspace_id UUID FK → workspaces,
    model VARCHAR(64) NOT NULL,
    layer VARCHAR(32),                    -- analysis / planning / generation / evaluation
    node VARCHAR(64),                     -- requirement_extractor / pattern_recommend
    input_tokens INT NOT NULL,
    output_tokens INT NOT NULL,
    cost DECIMAL(10,6) NOT NULL,
    latency_ms INT,
    cached BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ
);

-- budget_configs: 工作空间预算配置
CREATE TABLE budget_configs (
    workspace_id UUID PK FK → workspaces,
    monthly_budget_usd DECIMAL(10,2),
    alert_threshold DECIMAL(3,2) DEFAULT 0.9,  -- 90% 触发告警
    auto_downgrade BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ
);
```

### 5.2 E3 — 会话历史数据

```sql
-- sessions: 会话（块 A 已建表，此处补充字段说明）
-- id, workspace_id, user_id, title, session_type, status,
-- summary, message_count, token_count, cost_usd,
-- rating, tags, created_at, last_message_at, deleted_at

-- session_messages: 会话消息
CREATE TABLE session_messages (
    id UUID PK,
    session_id UUID FK → sessions ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,            -- user / assistant / system / tool
    content TEXT NOT NULL,
    content_type VARCHAR(32) DEFAULT 'text',
    attachments JSONB DEFAULT '[]',        -- [{type, url, name, size}]
    metadata JSONB DEFAULT '{}',           -- {model, tokens, latency}
    turn_index INT NOT NULL,
    token_count INT DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    model_used VARCHAR(64),
    created_at TIMESTAMPTZ,
    UNIQUE(session_id, turn_index)
);

CREATE INDEX idx_messages_session ON session_messages(session_id);
CREATE INDEX idx_messages_fts ON session_messages
  USING GIN(to_tsvector('simple', content));
```

### 5.3 E4 — 文档管理数据

```sql
-- uploaded_documents: 已上传文档（块 A 已建表，此处补充字段说明）
-- id, workspace_id, user_id, original_filename, storage_path,
-- file_size, file_type, mime_type, file_hash (SHA-256),
-- title, description, page_count, word_count, source_url,
-- processing_status (pending/processing/indexed/failed),
-- entity_count, relation_count, tags, is_deleted,
-- session_id, task_id, created_at, deleted_at

CREATE INDEX idx_documents_fts ON uploaded_documents
  USING GIN(to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,'')));
CREATE INDEX idx_documents_hash ON uploaded_documents(file_hash);
```

### 5.4 E2 — OpenTelemetry Span 属性

```python
# 每个 Span 携带的属性
SPAN_ATTRIBUTES = {
    "task_id": "...",
    "workspace_id": "...",
    "layer": "analysis",
    "node": "requirement_extractor",
    "model": "deepseek-v3",
    "iteration": 1,
}
```

---

## 6. 要新增的文件

```
app/llm_gateway/
├── __init__.py
├── router.py                              # 模型路由策略（叠加块 A 核心之上）
├── cost_tracker.py                        # 成本追踪（叠加块 A 核心之上）
├── budget_controller.py                   # ⭐ 预算控制（新增）
├── cache.py                               # 语义缓存（叠加块 A 核心之上）
├── rate_limiter.py                        # ⭐ 流控（新增）
└── observability.py                       # LangFuse 集成（可选）

app/observability/
├── __init__.py
├── tracing.py                             # OpenTelemetry 追踪
├── metrics.py                             # Prometheus 指标
└── alerts.yml                             # 告警规则

app/session_history/
├── __init__.py
├── service.py                             # 会话 CRUD + 搜索 + 导出
├── models.py                              # Session, SessionMessage Pydantic 模型
├── repository.py                          # 数据库访问层
├── search.py                              # 会话全文搜索
├── exporter.py                            # Markdown / JSON 导出
├── summarizer.py                          # LLM 自动生成标题和摘要
└── cleanup.py                             # 老化清理策略

app/document_management/
├── __init__.py
├── service.py                             # 文档上传/列表/删除/重索引
├── models.py                              # UploadedDocument Pydantic 模型
├── repository.py                          # 数据库访问层
├── search.py                              # 文档混合搜索（FTS + 语义）
├── preview.py                             # 文档预览生成
├── deduplication.py                       # SHA-256 去重
├── storage.py                             # MinIO 存储后端
├── csv_loader.py                          # ⭐ CSV 双通路索引（行级+列级）
└── batch_operations.py                    # 批量导入/导出/删除

app/web_indexing/                          # ⭐⭐ Web 资源索引（新增模块）
├── __init__.py
├── web_loader.py                          # 单次 URL 抓取+正文提取
├── web_crawler.py                         # 同域递归爬虫
├── web_sync.py                            # 定时同步（Celery Beat）
└── search_fallback.py                     # ⭐ 搜索引擎回退

app/multimodal/                            # ⭐⭐ 多模态（新增模块）
├── __init__.py
├── clip_encoder.py                        # CLIP 双塔编码（visual_emb + text_emb）
├── image_chunk_store.py                   # ImageChunk 存储
├── multimodal_search.py                   # 以图搜图/文搜图/图文混合
└── image_preview.py                       # 图片预览+缩略图

app/collaboration/                         # ⭐ 协作文档（新增模块）
├── __init__.py
├── service.py                             # 评论/建议/审批
├── comment.py                             # 行内评论
├── suggestion.py                          # 建议修改
└── changelog.py                           # 变更历史

app/integrations/
├── __init__.py
├── hub.py                                 # IntegrationHub
└── webhook.py                             # Webhook 发送

app/batch/                                 # ⭐ 批量处理与定时任务
├── __init__.py
├── scheduler.py                           # Celery Beat 配置
├── batch_operations.py                    # 批量导入/导出/删除/重索引
└── tasks.py                               # Celery 任务定义

app/api/routes/
├── sessions.py                            # 会话历史接口
├── documents.py                           # 文档管理接口
├── csv_import.py                          # ⭐ CSV 导入接口
├── web_indexing.py                        # ⭐ Web 索引接口
├── multimodal.py                          # ⭐ 多模态检索接口
├── collaboration.py                       # ⭐ 协作接口
├── batch.py                               # ⭐ 批量任务接口
└── integrations.py                        # 集成配置接口

tests/unit/
├── test_llm_gateway.py
├── test_session_history.py
├── test_document_management.py
├── test_csv_loader.py                     # ⭐ CSV 双通路索引测试
├── test_web_loader.py                     # ⭐ Web 加载测试
├── test_clip_encoder.py                   # ⭐ 多模态编码测试
├── test_collaboration.py                  # ⭐ 协作文档测试
├── test_batch_tasks.py                    # ⭐ 批量任务测试
├── test_search_fallback.py                # ⭐ 搜索引擎回退测试
└── test_integrations.py

tests/integration/
├── test_llm_gateway.py
├── test_session_history.py
├── test_document_management.py
├── test_csv_indexing.py                   # ⭐ CSV 索引集成测试
├── test_web_crawling.py                   # ⭐ Web 爬虫集成测试
├── test_multimodal_search.py              # ⭐ 多模态检索集成测试
├── test_collaboration_flow.py             # ⭐ 协作全流程测试
├── test_batch_operations.py               # ⭐ 批量操作集成测试
├── test_search_fallback.py                # ⭐ 搜索回退集成测试
└── test_integrations.py
```

---

## 7. 模块联通（输入/输出接口）

### 本块对外输出

```
输出（增强块 D）:
  - app/llm_gateway/ → 替换块 C/D 中的裸 LLM 调用
  - app/observability/ → 为块 D 的 API 添加追踪
  - app/api/routes/sessions.py → 新路由注册到 app/main.py
  - app/api/routes/documents.py → 新路由注册到 app/main.py
```

### 本块对外输入

```
输入 ← 块 A:
  - app/main.py: FastAPI 应用实例（注册新路由）
  - app/auth/deps.py: 权限检查（复用）
  - app/core/llm.py: LLM 客户端（Gateway 包装）
  - app/models/*.py: 数据模型（sessions/docs 表）

输入 ← 块 B:
  - app/knowledge_layer/ingestion/document_loader.py（文档管理复用）
  - app/knowledge_layer/ingestion/chunker.py（文档管理复用）

输入 ← 块 D:
  - app/task_manager.py: 任务管理器（会话历史关联任务）
  - app/orchestrator/main_graph.py: 编译后的 Orchestrator（Gateway 替换 LLM 调用）
```

### 关键接口

```python
# LLM Gateway 接口
class LLMGateway:
    async def complete(
        self,
        prompt: str,
        task_type: str,                    # "analysis.requirement" / "planning.pattern"
        workspace_id: str,
        response_format: dict = None,
    ) -> LLMResponse:
        """自动路由模型 + 追踪成本 + 语义缓存。"""
        ...

# SessionHistoryService 接口
class SessionHistoryService:
    async def list_sessions(self, workspace_id, page, page_size, ...) -> PageResult
    async def get_session(self, session_id) -> Session
    async def add_message(self, session_id, role, content, ...) -> SessionMessage
    async def search_messages(self, workspace_id, query, ...) -> list[SearchResult]
    async def export_session(self, session_id, format) -> str | bytes
    async def cleanup_expired(self, workspace_id) -> int

# DocumentManagementService 接口
class DocumentManagementService:
    async def upload(self, file, workspace_id, user_id) -> UploadedDocument
    async def list_documents(self, workspace_id, page, page_size, ...) -> PageResult
    async def get_preview(self, document_id) -> dict
    async def search_documents(self, workspace_id, query, ...) -> list[ScoredDoc]
    async def delete_document(self, document_id) -> None
    async def reindex(self, document_id) -> str   # 返回 task_id
```

---

## 8. 完整链路

```
E1 — LLM Gateway 调用链路:
  块 C/D 的 Node 调用 gateway.complete(prompt, task_type, workspace_id)
    → Router.route(task_type) → 选择模型（deepseek-v3 / gpt-4o-mini）
    → Cache.lookup(prompt) → 命中则直接返回
    → CostTracker.track() → 记录开始
    → 实际 LLM 调用（OpenAI SDK）
    → CostTracker.track() → 记录结束（input_tokens, output_tokens, cost）
    → BudgetController.check(workspace_id) → 超预算则告警
    → 返回 LLMResponse

E3 — 会话历史链路:
  用户创建会话:
    POST /api/v1/sessions
      → Auth 中间件验证
      → SessionService.create(workspace_id, title, type)
      → 写入 sessions 表
      → 返回 session 信息

  用户查看历史会话:
    GET /api/v1/sessions?workspace_id=xxx&page=1&q=订单
      → SessionService.list() → FTS 搜索标题+摘要
      → 返回分页结果

  用户查看某次会话:
    GET /api/v1/sessions/{id}/messages?page=1
      → SessionService.get_messages()
      → 返回消息列表（按 turn_index 排序）

E4 — 文档管理链路:
  用户上传文档:
    POST /api/v1/documents/upload (multipart/form-data)
      → DocumentService.upload()
        → 文件大小校验（≤ 50MB）
        → SHA-256 哈希 → 去重检测
        → 存储到 MinIO（prd-docs/{ws_id}/{yyyy}/{mm}/{hash}.ext）
        → 写入 uploaded_documents 表
        → 触发异步处理（Celery 或 asyncio）
      → 返回 document 信息

  文档搜索:
    GET /api/v1/documents/search?q=订单&workspace_id=xxx
      → DocumentSearchService.search()
        → 路1: FTS 搜索 title + description
        → 路2: 语义搜索 embedding
        → RRF 融合
      → 返回结果列表
```

---

## 9. 测试用例

### 9.1 LLM Gateway 测试

```python
# tests/unit/test_llm_gateway.py
async def test_gateway_routes_correct_model():
    """验证模型路由按 task_type 正确选择。"""
    gateway = LLMGateway()
    model = gateway.router.route("analysis.requirement")
    assert model == "deepseek-v3"
    model = gateway.router.route("evaluation.scoring")
    assert model == "gpt-4o-mini"

async def test_gateway_tracks_cost():
    """验证成本追踪。"""
    result = await gateway.complete("Hello", "test", "ws-1")
    assert result.cost > 0
    assert result.input_tokens > 0
    assert result.model is not None

async def test_semantic_cache_hit():
    """验证语义缓存命中。"""
    r1 = await gateway.complete("What is PRD?", "test", "ws-1")
    r2 = await gateway.complete("What is PRD?", "test", "ws-1")
    assert r2.cached == True  # 第二次命中缓存
```

### 9.2 会话历史测试

```python
# tests/integration/test_session_history.py
async def test_create_and_list_sessions():
    """验证创建会话 → 列表可见。"""
    svc = SessionHistoryService()
    session = await svc.create("ws-1", "测试会话", "generate")
    assert session.id is not None

    result = await svc.list_sessions("ws-1")
    assert len(result.items) >= 1
    assert any(s.title == "测试会话" for s in result.items)

async def test_add_and_search_messages():
    """验证添加消息 → 可搜索到。"""
    msg = await svc.add_message(session_id, "user", "订单服务用什么数据库？")
    assert msg.turn_index == 0

    results = await svc.search_messages("ws-1", "订单服务")
    assert len(results) >= 1

async def test_export_session():
    """验证会话导出。"""
    md = await svc.export_session(session_id, "markdown")
    assert "#" in md  # Markdown 格式
    assert "订单服务" in md

async def test_cleanup_policy():
    """验证老化清理。"""
    deleted = await svc.cleanup_expired("ws-1")
    assert deleted >= 0
```

### 9.3 文档管理测试

```python
# tests/integration/test_document_management.py
async def test_upload_and_list():
    """验证上传 → 列表可见。"""
    svc = DocumentManagementService()
    doc = await svc.upload(test_pdf_bytes, "ws-1", "user-1")
    assert doc.file_type == "pdf"
    assert doc.processing_status == "pending"

    result = await svc.list_documents("ws-1")
    assert len(result.items) >= 1

async def test_deduplication():
    """验证 SHA-256 去重。"""
    doc1 = await svc.upload(same_content, "ws-1", "user-1")
    doc2 = await svc.upload(same_content, "ws-1", "user-1")
    assert doc1.id == doc2.id  # 相同哈希返回同一个记录

async def test_search():
    """验证文档搜索。"""
    results = await svc.search_documents("ws-1", "订单设计")
    assert len(results) > 0

async def test_pdf_preview():
    """验证 PDF 预览。"""
    preview = await svc.get_preview(doc_id)
    assert "text_preview" in preview
    assert "page_count" in preview
```

---

## 10. 验收标准

### 必须满足

```bash
# 1. 技术栈合规
pytest tests/test_tech_stack_compliance.py -v

# 2. 类型检查 + 风格
mypy app/ --strict --ignore-missing-imports
ruff check app/ tests/

# 3. 全部测试通过（含块 A/B/C/D 全部回归）
pytest tests/ -v --tb=short
# 100% passed, 0 skipped

# 4. 无 TODO 残留
grep -rn "TODO\|FIXME\|NotImplementedError" app/ --include="*.py" || echo "CLEAN"
```

### 联通性测试

```bash
# 启动新容器
docker compose up -d jaeger prometheus minio

# E1: LLM Gateway
pytest tests/integration/test_llm_gateway.py -v
# 期望: 模型路由正确 + 成本可追踪 + 缓存命中

# E2: 观测性
pytest tests/integration/test_observability.py -v
# 期望: Prometheus 指标可收集 / Jaeger Span 可导出

# E3: 会话历史
pytest tests/integration/test_session_history.py -v
# 期望: 创建会话 → 加消息 → 搜索 → 导出 → 清理

# E4: 文档管理
pytest tests/integration/test_document_management.py -v
# 期望: 上传 → 去重 → 预览 → 搜索 → 删除

# E5: 端到端回归（最重要的验收）
pytest tests/e2e/test_full_flow.py -v --slow
# 期望: 块 D 的全链路仍然正常工作

# E6: CSV 双通路索引
pytest tests/integration/test_csv_indexing.py -v
# 期望: CSV 上传→行级+列级均可检索

# E7: Web 资源索引
pytest tests/integration/test_web_crawling.py -v
# 期望: URL 抓取→正文提取→知识图谱写入

# E8: 多模态检索
pytest tests/integration/test_multimodal_search.py -v
# 期望: 以图搜图返回相似架构图

# E9: 协作文档
pytest tests/integration/test_collaboration_flow.py -v
# 期望: 评论→建议修改→审批→变更历史

# E10: 批量操作
pytest tests/integration/test_batch_operations.py -v
# 期望: 批量导入→批量重索引→定时任务触发

# E11: 搜索引擎回退
pytest tests/integration/test_search_fallback.py -v
# 期望: 本地无结果→自动触发网络搜索→返回结果
```

### 完成后状态

```
✅ LLM Gateway 企业增强（预算控制+流控+LangFuse）
✅ 分布式追踪链路完整（Jaeger 可见）
✅ Prometheus 指标可收集
✅ 用户可查看历史会话、搜索对话内容
✅ 用户可上传文档、预览、搜索
✅ 文档上传自动去重
✅ CSV 文件行级+列级双通路索引
✅ Web URL 可抓取、可爬取、可定时同步
✅ 以图搜图/文搜图/图文混合检索可用
✅ 协作文档（评论+建议+变更历史）
✅ Celery Beat 定时任务就绪
✅ 本地无结果时自动触发网络搜索
✅ Webhook 可配置
✅ 块 A/B/C/D 全部回归测试仍然全绿
🎉 系统完整可用
```

---

## 附录：各块文件依赖关系

```
块 A: 基础设施
  └── 提供: DB Session, Auth, LLM, Contracts

块 B: 知识层
  ├── 依赖: 块 A 的 LLM + DB
  └── 提供: RetrievalPipeline

块 C: Agent 流水线
  ├── 依赖: 块 A 的 LLM + Contracts
  ├── 依赖: 块 B 的 Pipeline
  └── 提供: 4 个 StateGraph

块 D: 全链路串联
  ├── 依赖: 块 A 的 FastAPI + Auth
  ├── 依赖: 块 B 的 Pipeline
  ├── 依赖: 块 C 的 4 个 Graph
  └── 提供: 完整 API 服务

块 E: 企业功能
  ├── 依赖: 块 A 的 DB + Auth
  ├── 依赖: 块 B 的 DocumentLoader
  ├── 依赖: 块 D 的 API 服务
  └── 增强: 块 C/D 的 LLM 调用（替换为 Gateway）
```
