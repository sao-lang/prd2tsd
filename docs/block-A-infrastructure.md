# 块 A：基础设施与质量底座

> 关联总文档：`prd2tsd.md` §1.1 多租户与权限体系、§1.2 LLM Gateway（核心部分）、§8 完整项目目录结构、§9.1 Docker Compose、§9.2 API 接口完整列表（auth/workspace 部分）、§11 数据安全与隐私、§13 CI/CD 流水线
> 
> 本块完成后，后续块 B/C/D/E 都依赖本块产出的数据模型、Auth 中间件、LLM Gateway 和数据脱敏引擎。

---

## 1. 需求描述

搭建项目骨架、质量基础设施、数据模型、认证授权和多租户中间件，使系统具备最基本的「可启动、可登录、可建工作空间」能力。

这是所有后续开发的基础，**必须先完成本块才能进入块 B**。

### 核心功能列表

1. **项目脚手架**：pyproject.toml、requirements.txt、docker-compose.yml、.env.example
2. **基础设施连接管理**：统一管理 PostgreSQL/Redis/MinIO/Neo4j 四大外服连接的生命周期（初始化/健康检查/优雅关闭），块 A 启用 PostgreSQL，其余预留
3. **质量门禁**：pytest 配置、ruff/mypy、技术栈合规测试、注释完整性测试
4. **数据模型**：所有数据库表的 SQLAlchemy 模型 + alembic 迁移
4. **认证授权**：JWT 签发/验证、RBAC 权限检查、FastAPI 中间件
5. **多租户**：工作空间 CRUD、团队成员管理、租户上下文传递
6. **LLM Gateway 核心**：Provider 抽象层（多模型统一接口）、模型路由（task_type→model）、成本追踪（每次调用记 token+cost）、语义缓存（相同查询命中不重复调 LLM）
7. **模型配置中心**：各类模型（LLM/Embedding/Rerank/Judge/Vision）的 API Key、模型名、Base URL 统一管理；支持环境变量注入、API 动态注入、配置文件兜底三级优先级；所有涉及模型调用的地方统一从此获取配置
8. **API 骨架**：FastAPI 入口、健康检查、auth/workspace 路由、model_config 管理路由
9. **Contracts**：所有跨 Layer 的接口定义和数据模型（含模型配置数据模型）
10. **数据安全**：数据分类分级（L1-L4）、数据脱敏引擎（LLM 调用前自动脱敏）、审计日志（哈希链不可篡改）
11. **CI/CD 流水线**：GitHub Actions（PR 自动跑 lint + type-check + test + 技术栈合规）

---

## 2. 目标

| 目标 | 衡量标准 |
|------|---------|
| 项目可启动 | `docker compose up -d` 后所有容器正常运行 |
| 数据库可连接 | `pytest tests/integration/test_db_connection.py` PASS |
| Auth 流程完整 | register → login → access → refresh → logout 全链路可跑通 |
| 质量门禁生效 | 引入 langchain 时 `test_tech_stack_compliance.py` 会红 |
| 多租户可用 | 可创建 workspace、添加成员、切换租户上下文 |
| Contract 就绪 | `contracts/interfaces.py` 定义了所有 Layer 的接口签名 |
| 模型配置中心可用 | 支持 5 种模型类型（LLM/Embedding/Rerank/Judge/Vision）的 API Key/Base URL/模型名配置 |
| 三级配置优先级生效 | 环境变量→.env 文件→代码默认值，高优先级覆盖低优先级 |
| API 动态注入可用 | `PUT /api/v1/model-config` 修改配置后，后续模型调用立即使用新配置 |
| 涉及模型调用的模块统一接入 | Provider/Router/Embedding/Rerank/Judge 全部从 ModelConfigManager 获取配置 |

---

## 3. 使用技术栈

```yaml
# === 强制使用 ===
web_framework: fastapi>=0.110 + uvicorn
orm: sqlalchemy 2.0 + asyncpg          # 异步模式
migration: alembic
config: pydantic-settings>=2.x
jwt: python-jose
password: passlib + bcrypt
test: pytest>=8.0 + pytest-asyncio
lint: ruff
type_check: mypy

# === LLM Gateway（核心，所有后续块依赖）===
llm_provider:
  primary: deepseek-v3                 # 主模型
  fallback: gpt-4o-mini                # 降级模型
  judge: gpt-4o-mini                   # 评测用低成本模型
  sdk: openai>=1.0                     # OpenAI SDK（兼容 DeepSeek API 格式）

llm_gateway:
  - provider.py                        # Provider 抽象层
  - router.py                          # 模型路由
  - cost_tracker.py                    # 成本追踪
  - cache.py                           # 语义缓存
  - models.py                          # 模型配置 Pydantic 模型（ModelType/ModelConfig/RoutingRule 等）
  - config_manager.py                  # 模型配置管理器（三级优先级、运行时动态更新）
  - __init__.py                        # LLMGateway 门面类（统一对外接口）

# === 数据安全 ===
data_security:
  data_masking: re + hashlib           # 正则检测 + SHA-256 哈希
  audit_log: hashlib + postgres        # 哈希链审计日志
  classification: jsonb + postgres     # 数据分类分级（L1-L4）

# === CI/CD ===
ci_cd:
  pr_check: github-actions/ci.yml      # PR 自动跑 lint + type-check + test
  deploy_prod: github-actions/deploy-prod.yml  # 手动触发生产部署
  backup: github-actions/backup.yml    # 定时备份

# === 基础设施服务 ===
services:
  database: postgres:16 + pgvector       # 主数据库 + 向量检索（块 A 启用）
  cache: redis:7-alpine                  # 缓存/队列/会话（块 B 起启用）
  object_store: minio/minio:latest       # 对象存储（块 D 起启用）
  graph: neo4j:5-enterprise              # 知识图谱（块 B 起启用）

# === 基础设施 SDK（供 app/core/connections.py 统一管理，应用层不直接调用）===
infra_sdks:
  postgres_driver: asyncpg               # PostgreSQL 异步驱动
  redis_client: redis-py[hiredis]>=5.0   # Redis 客户端
  minio_client: minio>=7.0               # MinIO S3 客户端
  neo4j_client: neo4j>=5.0               # Neo4j Bolt 驱动

# === 应用层禁止引入（基础设施驱动不受此限）===
forbidden_app_deps:
  - langchain, langchain-community, langchain-openai
  - chromadb, qdrant-client, weaviate-client
  - flask, django
  - sqlite                              # 不允许生产环境用 SQLite
```

---

## 4. Coding 约束

```python
# ✅ 每个 public 函数必须有 type hint + Google 风格 docstring
def get_user(self, user_id: uuid.UUID) -> User | None:
    """根据 ID 获取用户。

    Args:
        user_id: 用户 UUID。

    Returns:
        User 对象，不存在时返回 None。

    Raises:
        ConnectionError: 数据库连接失败时抛出。
    """
    ...

# ❌ 禁止模式
def foo():                    # 无 type hint
    pass                       # pass 占位
    # TODO: implement          # TODO
    raise NotImplementedError  # 未实现
    ...                        # 省略号占位
    # type: ignore[xxx]        # 除非有明确理由注释

# ✅ 允许的跨 Phase 标记
# VIBE_DEFER(块 C): 此处接入 Analysis Layer，当前返回 Mock 数据
```

### 代码行数限制

```
每个函数 ≤ 50 行（超过必须拆）
每个文件 ≤ 300 行（超过必须拆）
每个类 ≤ 200 行（超过必须拆）
```

---

## 5. 数据结构

### 5.1 核心表

```sql
-- users: 用户账号
CREATE TABLE users (
    id UUID PK,
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    auth_provider VARCHAR(32) NOT NULL,   -- 'jwt' / 'keycloak' / 'wecom'
    auth_id VARCHAR(255) NOT NULL,
    status VARCHAR(16) DEFAULT 'active',
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    UNIQUE(auth_provider, auth_id)
);

-- organizations: 组织
CREATE TABLE organizations (
    id UUID PK,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(64) UNIQUE NOT NULL,
    plan VARCHAR(32) DEFAULT 'free',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ
);

-- workspaces: 工作空间（多租户单元）
CREATE TABLE workspaces (
    id UUID PK,
    organization_id UUID FK → organizations,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(64) NOT NULL,
    knowledge_scope VARCHAR(32) DEFAULT 'workspace',
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ,
    UNIQUE(organization_id, slug)
);

-- roles: 角色（系统预置 + 自定义）
CREATE TABLE roles (
    id UUID PK,
    organization_id UUID FK → organizations,
    name VARCHAR(64) NOT NULL,
    is_system BOOLEAN DEFAULT FALSE,
    permissions JSONB NOT NULL,        -- ["workspace:read", "prd:write", ...]
    created_at TIMESTAMPTZ
);

-- team_members: 团队成员
CREATE TABLE team_members (
    id UUID PK,
    workspace_id UUID FK → workspaces,
    user_id UUID FK → users,
    role_id UUID FK → roles,
    joined_at TIMESTAMPTZ,
    UNIQUE(workspace_id, user_id)
);
```

### 5.2 Auth 相关数据流

```
用户注册 → users 表写入
         → 自动创建 personal workspace
         → 返回 JWT (access_token + refresh_token)

JWT Payload:
{
  "sub": "user-uuid",
  "org_id": "org-uuid",
  "ws_id": "workspace-uuid",
  "permissions": ["workspace:read", "prd:write"],
  "exp": 1712345678
}
```

### 5.3 Contract 接口定义

```python
# contracts/interfaces.py — 所有 Layer 的接口签名（块 A 定义后不允许修改）

class RetrievalContext(BaseModel):
    """知识检索结果"""
    query: str
    docs: list[ScoredDoc]
    search_mode: str

class AnalysisResult(BaseModel):
    """分析层输出"""
    project_name: str
    summary: str
    requirements: list[Requirement]
    constraints: list[Constraint]
    # ...

class PlanningResult(BaseModel):
    """规划层输出"""
    architecture_pattern: str
    tech_stack: list[TechChoice]
    components: list[Component]
    # ...

class GenerationResult(BaseModel):
    """生成层输出"""
    content: str              # Markdown 文档
    sections: dict[str, str]
    # ...

class EvaluationReport(BaseModel):
    """评测报告"""
    overall_score: float
    dimension_scores: dict
    conclusion: str
    # ...
```

### 5.4 模型配置数据模型

```python
# contracts/models.py（模型配置部分）— 所有模型调用方统一使用

from enum import Enum
from pydantic import BaseModel, Field

class ModelType(str, Enum):
    """模型类型枚举 — 涵盖所有模型调用场景"""
    LLM = "llm"               # 大语言模型（生成/对话）
    EMBEDDING = "embedding"   # 向量嵌入
    RERANK = "rerank"         # 重排序
    JUDGE = "judge"           # 评测模型（低成本）
    VISION = "vision"         # 视觉/多模态
    AUDIO = "audio"           # 语音
    IMAGE = "image"           # 图像生成

class ProviderType(str, Enum):
    """支持的模型供应商"""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    AZURE_OPENAI = "azure_openai"
    COHERE = "cohere"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"

class ModelConfig(BaseModel):
    """单个模型的完整配置 — 所有模型调用方统一使用此结构"""
    provider: ProviderType = ProviderType.OPENAI
    api_key: str = ""                    # API 密钥
    base_url: str = ""                   # API 端点 Base URL
    default_model: str = ""              # 默认模型名/ID
    config: dict[str, Any] = {}          # 额外参数（temperature, max_tokens 等）
    timeout: int = 60                    # 超时秒数
    max_retries: int = 3                 # 重试次数

class ModelEndpointConfig(BaseModel):
    """某模型类型的完整配置（支持多供应商、多模型）"""
    type: ModelType
    providers: dict[str, ModelConfig] = {}   # key=供应商名, value=配置
    default_provider: str = ""               # 默认供应商
    default_model: str = ""                  # 默认模型名

class RoutingRule(BaseModel):
    """模型路由规则 — task_type → 模型映射"""
    type: ModelType = ModelType.LLM          # 路由到的模型类型
    provider: str = ""                       # 路由到的供应商
    model: str = ""                          # 路由到的具体模型名
    temperature: float | None = None
    max_tokens: int | None = None
    config: dict[str, Any] = {}

class FullModelConfig(BaseModel):
    """完整模型配置（所有类型 + 路由规则）"""
    endpoints: dict[ModelType, ModelEndpointConfig] = {}
    routing_rules: dict[str, RoutingRule] = {}   # key = task_type

class ModelConfigUpdate(BaseModel):
    """模型配置更新请求体（API 动态注入用）"""
    type: ModelType
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    config: dict[str, Any] | None = None
    timeout: int | None = None
    max_retries: int | None = None

class RoutingRuleUpdate(BaseModel):
    """路由规则更新请求体（API 动态注入用）"""
    task_type: str
    type: ModelType | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    config: dict[str, Any] | None = None
```

---

## 6. 要新增的文件

```
prd2tsd-agents/
├── pyproject.toml                     # ruff + mypy + pytest 配置
├── requirements.txt                   # 仅块 A 需要的依赖
├── .env.example                       # 环境变量模板
├── docker-compose.yml                 # postgres + pgvector
├── Dockerfile                         # API 服务镜像
│
├── contracts/
│   ├── __init__.py
│   ├── interfaces.py                  # 所有 Layer 接口定义
│   └── models.py                      # 跨 Layer 数据模型
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     # PR 自动跑 lint + type-check + test + 技术栈合规
│       ├── deploy-prod.yml            # 手动触发生产部署
│       └── backup.yml                 # 定时备份（PostgreSQL + Neo4j + MinIO）
│
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI 应用入口
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # pydantic-settings 配置
│   │   ├── llm.py                     # LLM 客户端（OpenAI SDK 兼容 DeepSeek）
│   │   ├── logger.py                  # 结构化日志
│   │   └── exceptions.py             # 自定义异常基类
│   │
│   ├── llm_gateway/                   # ★ LLM Gateway 核心（所有 Agent 依赖）
│   │   ├── __init__.py                # LLMGateway 门面类（统一对外接口）
│   │   ├── models.py                  # ★ 模型配置 Pydantic 模型（ModelType/ModelConfig/RoutingRule 等）
│   │   ├── config_manager.py          # ★ 模型配置管理器（三级优先级、运行时动态更新、配置合并）
│   │   ├── provider.py                # Provider 抽象层（OpenAI/DeepSeek/Claude 统一接口，从 config_manager 读取配置）
│   │   ├── router.py                  # 模型路由（根据 task_type 选择模型，从 config_manager 读取路由规则）
│   │   ├── cost_tracker.py            # 成本追踪（记录 input_tokens/output_tokens/cost）
│   │   └── cache.py                   # 语义缓存（命中缓存不重复调 LLM）
│   │
│   ├── security/                      # ★ 数据安全
│   │   ├── __init__.py
│   │   ├── data_classifier.py         # 数据分类分级（L1-L4 标签）
│   │   ├── data_masking.py            # 数据脱敏引擎（自动检测替换 API Key/Token/密码等）
│   │   └── audit_logger.py            # 审计日志（哈希链不可篡改）
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                    # SQLAlchemy Base + 通用 Mixin
│   │   ├── user.py                    # users 表
│   │   ├── organization.py            # organizations 表
│   │   ├── workspace.py               # workspaces 表
│   │   ├── role.py                    # roles 表
│   │   └── team_member.py             # team_members 表
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py                  # Auth 相关 Pydantic 模型
│   │   ├── token_manager.py           # JWT 签发/验证/刷新
│   │   ├── permissions.py             # PermissionChecker（RBAC + ABAC）
│   │   ├── middleware.py              # FastAPI 中间件（提取用户+租户）
│   │   └── deps.py                    # get_current_user, require_permission
│   │
│   └── api/
│       ├── __init__.py
│       ├── deps.py                    # 全局依赖注入
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── auth.py                # login / refresh / logout / me
│       │   ├── workspace.py           # workspace CRUD + members
│       │   └── model_config.py        # ★ 模型配置管理 CRUD（GET/PUT 各类模型配置和路由规则）
│       └── schemas/
│           ├── __init__.py
│           ├── request.py             # 请求体模型
│           ├── response.py            # 响应体模型
│           └── model_config.py        # ★ 模型配置相关请求/响应 Schema
│
├── storage/                           # 本地存储（gitkeep）
│   └── .gitkeep
│
├── scripts/
│   └── init_db.py                     # 数据库初始化脚本
│
└── tests/
    ├── conftest.py                    # pytest fixtures（测试 DB、测试客户端）
    ├── test_tech_stack_compliance.py  # 技术栈合规检测
    ├── test_lint.py                   # 注释完整性 + ruff 零错误
    ├── unit/
    │   ├── test_models.py             # 数据模型单元测试
    │   ├── test_auth.py               # Auth 单元测试（JWT、权限检查）
    │   ├── test_model_config.py       # ★ 模型配置单元测试（三级优先级/路由/动态更新/Key掩码）
    │   ├── test_llm_gateway.py        # LLM Gateway 单元测试（配置解析/成本/缓存）
    │   ├── test_data_masking.py       # 数据脱敏单元测试（各类型敏感数据检测）
    │   ├── test_audit_logger.py       # 审计日志单元测试（哈希链验证）
    │   └── test_workspace.py          # 工作空间单元测试
    └── integration/
        ├── test_db_connection.py      # PostgreSQL 联通性测试
        ├── test_auth_flow.py          # 完整 Auth 流程测试
        ├── test_model_config_api.py   # ★ 模型配置 API 集成测试（GET/PUT/DELETE）
        ├── test_llm_gateway.py        # LLM Gateway 集成测试（真实模型调用）
        ├── test_audit_log.py          # 审计日志集成测试
        └── test_workspace_api.py      # 工作空间 API 集成测试
```

---

## 7. 模型配置中心设计

> 设计原则：**所有涉及模型调用的地方，必须从 ModelConfigManager 获取配置**，不允许硬编码 API Key/Base URL/模型名。
> 涵盖范围：LLM（主模型/生成）、Embedding（向量化）、Rerank（重排序）、Judge（评测）、Vision（视觉）等全部模型类型。

### 7.1 三级配置优先级体系

```
优先级 1（最高）: API 动态注入（运行时内存态）
  └─ PUT /api/v1/model-config → ModelConfigManager.update_config()
  └─ 立即生效，无需重启，不持久化（重启后由优先级 2/3 兜底）

优先级 2（中间） : 环境变量
  └─ MODEL_CONFIG__{TYPE}__{PROVIDER}__API_KEY
  └─ MODEL_CONFIG__{TYPE}__{PROVIDER}__BASE_URL
  └─ MODEL_CONFIG__{TYPE}__{PROVIDER}__DEFAULT_MODEL
  └─ MODEL_ROUTING__{TASK_TYPE}__TYPE / PROVIDER / MODEL

优先级 3（兜底） : .env 文件 + 代码默认值
  └─ .env 文件中定义 MODEL_CONFIG__xxx 系列变量
  └─ app/core/config.py 中 pydantic-settings 的 Field(default=...)
```

**合并规则**：高优先级字段覆盖低优先级，未设置的字段保留低优先级值（逐字段合并，非整体替换）。

### 7.2 核心组件

```
ModelConfigManager（配置管理器）
├── 职责：管理所有模型类型（LLM/Embedding/Rerank/Judge/Vision）的配置
├── 数据源：
│   ├── env_config: Settings 对象（环境变量 + .env 文件 + 默认值）
│   └── runtime_config: dict（API 动态注入，运行时内存态，最高优先级）
├── 核心方法：
│   ├── get_config(model_type, provider?) → ModelConfig
│   ├── update_config(type, provider, fields) → None      # API 注入
│   ├── update_routing_rule(task_type, rule) → None
│   ├── get_routing_rule(task_type) → RoutingRule
│   ├── resolve_model(task_type) → (ModelConfig, model_name)  # 路由+配置合并
│   └── reset_to_env() → None                              # 清除运行时配置
│
├── Provider（供应商抽象层）
│   ├── 职责：统一调用接口，从 ModelConfigManager 读取配置
│   ├── OpenAIProvider     → 兼容 OpenAI / DeepSeek / Azure OpenAI
│   ├── AnthropicProvider  → Claude 系列
│   ├── CohereProvider     → Rerank 系列
│   └── CustomProvider     → 自定义兼容任意 OpenAI-API 格式的服务
│
├── Router（模型路由）
│   ├── 职责：task_type → (model_type, provider, model_name)
│   ├── 路由规则来源：ModelConfigManager（支持动态更新）
│   └── 示例规则：
│       "analysis.requirement" → {type: llm, provider: deepseek, model: deepseek-chat}
│       "evaluation.scoring"   → {type: judge, provider: openai, model: gpt-4o-mini}
│       "embedding"            → {type: embedding, provider: openai, model: text-embedding-3-small}
│       "rerank"               → {type: rerank, provider: cohere, model: rerank-english-v3.0}
│
└── LLMGateway（门面类）
    ├── 职责：组装 Provider + Router + CostTracker + Cache + DataMasking
    ├── complete(prompt, task_type, workspace_id, **kwargs) → LLMResponse
    ├── embed(texts, task_type, **kwargs) → EmbeddingResponse
    └── rerank(query, docs, task_type, **kwargs) → RerankResponse
```

### 7.3 配置注入方式

#### 方式一：环境变量（部署时注入）

```bash
# .env 文件或 docker-compose environment
MODEL_CONFIG__LLM__DEEPSEEK__API_KEY=sk-xxx
MODEL_CONFIG__LLM__DEEPSEEK__BASE_URL=https://api.deepseek.com/v1
MODEL_CONFIG__LLM__DEEPSEEK__DEFAULT_MODEL=deepseek-chat

MODEL_CONFIG__EMBEDDING__OPENAI__API_KEY=sk-xxx
MODEL_CONFIG__EMBEDDING__OPENAI__BASE_URL=https://api.openai.com/v1
MODEL_CONFIG__EMBEDDING__OPENAI__DEFAULT_MODEL=text-embedding-3-small

MODEL_CONFIG__RERANK__COHERE__API_KEY=coh-xxx
MODEL_CONFIG__RERANK__COHERE__BASE_URL=https://api.cohere.com/v1
MODEL_CONFIG__RERANK__COHERE__DEFAULT_MODEL=rerank-english-v3.0

MODEL_CONFIG__JUDGE__OPENAI__API_KEY=sk-xxx
MODEL_CONFIG__JUDGE__OPENAI__BASE_URL=https://api.openai.com/v1
MODEL_CONFIG__JUDGE__OPENAI__DEFAULT_MODEL=gpt-4o-mini

MODEL_CONFIG__VISION__OPENAI__API_KEY=sk-xxx
MODEL_CONFIG__VISION__OPENAI__BASE_URL=https://api.openai.com/v1
MODEL_CONFIG__VISION__OPENAI__DEFAULT_MODEL=gpt-4o
```

#### 方式二：API 动态注入（运行时修改）

```http
### 修改 LLM DeepSeek 配置
PUT /api/v1/model-config
Content-Type: application/json

{
  "type": "llm",
  "provider": "deepseek",
  "api_key": "sk-new-key",
  "base_url": "https://api.deepseek.com/v1",
  "default_model": "deepseek-chat",
  "timeout": 120,
  "max_retries": 5
}

### 修改路由规则
PUT /api/v1/model-config/routing
Content-Type: application/json

{
  "task_type": "analysis.requirement",
  "type": "llm",
  "provider": "deepseek",
  "model": "deepseek-reasoner"
}

### 查询当前所有配置（返回结果会掩码 API Key）
GET /api/v1/model-config

### 查询某类型配置
GET /api/v1/model-config?type=llm&provider=deepseek

### 重置运行时配置（恢复到环境变量配置）
DELETE /api/v1/model-config/runtime
```

### 7.4 配置生效链路

```
场景：Agent Node 调用 LLM 生成 PRD 分析
─────────────────────────────────────────
gateway.complete(prompt, "analysis.requirement", "ws-1")
  │
  ├─ 1. ModelConfigManager.resolve_model("analysis.requirement")
  │      ├─ Router 查找 routing_rules["analysis.requirement"]
  │      │   → {type: llm, provider: deepseek}
  │      ├─ 获取 ModelConfig:
  │      │   ├─ runtime_config["llm"]["deepseek"]? （API 注入，最高优先级）
  │      │   ├─ env: MODEL_CONFIG__LLM__DEEPSEEK__* （环境变量）
  │      │   └─ default: {base_url: "https://api.deepseek.com/v1", ...}
  │      └─ 合并后返回 → {api_key, base_url, default_model: "deepseek-chat", ...}
  │
  ├─ 2. Provider.create("deepseek", config)
  │      └─ 用 config.api_key / config.base_url 初始化 OpenAI 客户端
  │
  ├─ 3. 数据脱敏引擎自动脱敏 prompt 中的敏感信息
  ├─ 4. 语义缓存查找命中 → 命中直接返回
  ├─ 5. Provider.complete(prompt, model=...) 调用实际 LLM
  ├─ 6. 成本追踪记录 token/cost
  ├─ 7. 审计日志记录本次调用
  └─ 8. 返回 LLMResponse
```

### 7.5 涉及模型调用的所有模块

| 模块 | 模型类型 | 配置来源 | 说明 |
|------|---------|---------|------|
| Analysis Layer | LLM | ModelConfigManager | PRD 分析、需求提取、约束识别 |
| Planning Layer | LLM | ModelConfigManager | 架构规划、技术选型、组件设计 |
| Generation Layer | LLM | ModelConfigManager | 文档生成、章节撰写 |
| Evaluation Layer | JUDGE | ModelConfigManager | 评分、评测、Review |
| Knowledge Base (块B) | EMBEDDING | ModelConfigManager | 文档向量化 |
| Knowledge Base (块B) | RERANK | ModelConfigManager | 检索结果重排序 |
| Knowledge Base (块B) | LLM | ModelConfigManager | Query 改写、Chunk 摘要 |
| Vision Service (块E) | VISION | ModelConfigManager | 图表/截图理解 |

### 7.6 API Key 安全

```python
# 1. 日志自动掩码 - 打印配置时 API Key 用 **** 替代
config.masked_api_key()  # → "sk-d***f456"

# 2. 数据脱敏引擎自动捕获 - prompt 中的 API Key 在进 LLM 前被脱敏
# 3. API 返回配置时自动掩码 - GET /api/v1/model-config 不返回明文 Key
# 4. 不持久化到数据库 - 运行时配置仅在内存中
```

---

## 8. 基础设施服务与连接管理

> 本块定义所有外部基础设施服务的连接生命周期管理，确保 PostgreSQL/Redis/MinIO/Neo4j 四大服务有统一的初始化、健康检查、优雅关闭机制。

### 8.1 设计原则

```
1. 统一入口：所有外部连接通过 ConnectionManager 注册和管理
2. Lazy Init：块 A 只启用 PostgreSQL，其他服务注册但不连接（后续块按需激活）
3. 环境变量驱动：连接配置来自 Settings（.env / 环境变量 / 默认值三级）
4. 优雅关闭：shutdown 时按依赖依赖顺序逐一切断
5. 连接自愈：连接丢失时自动重试（最多 max_retries 次）
```

### 8.2 核心组件

```
app/core/connections.py
├── ConnectionManager（统一入口）
│   ├── _connectors: dict[str, BaseConnector]  # 已注册的连接器
│   ├── _lifetime: "init" | "started" | "stopped"  # 生命周期状态
│   │
│   ├── register(name, connector)  → 注册连接器
│   ├── get(name)                  → 获取连接实例
│   ├── startup()                  → 启动所有活跃连接
│   ├── shutdown()                 → 按依赖顺序优雅关闭
│   ├── health_check()             → 批量检查所有连接状态
│   └── is_healthy(name)           → 查询某连接健康状态
│
├── BaseConnector（连接器抽象基类）
│   ├── name: str                  # 连接器名称
│   ├── enabled: bool              # 当前是否启用
│   ├── config: dict               # 连接配置
│   │
│   ├── connect() → bool           # 建立连接
│   ├── disconnect()               # 断开连接
│   ├── is_connected() → bool      # 检查连接状态
│   └── health() → ConnHealth      # 返回健康状态详情
│
├── PostgreSQLConnector
│   ├── 基于 asyncpg + SQLAlchemy async engine
│   ├── get_session() → AsyncGenerator[AsyncSession]
│   ├── pool_size / max_overflow 可配置
│   └── 块 A 启用
│
├── RedisConnector（预留，块 B/C 启用）
│   ├── 基于 redis.asyncio
│   ├── get_client() → Redis
│   ├── 语义缓存 / 消息队列 / 会话存储 共用同一个连接池
│   └── 块 A: 注册但不连接（lazy init）
│
├── MinIOConnector（预留，块 D/E 启用）
│   ├── 基于 minio.Minio
│   ├── get_client() → Minio
│   ├── 文档存储 / 备份 使用
│   └── 块 A: 注册但不连接（lazy init）
│
└── Neo4jConnector（预留，块 B 启用）
    ├── 基于 neo4j.AsyncGraphDatabase
    ├── get_driver() → AsyncDriver
    ├── 知识图谱读写
    └── 块 A: 注册但不连接（lazy init）
```

### 8.3 连接配置（环境变量）

```bash
# PostgreSQL（块 A 启用）
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/prd2tsd
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis（块 B 起启用）
REDIS_URL=redis://redis:6379/0
REDIS_POOL_SIZE=10

# MinIO（块 D 起启用）
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=prd2tsd
MINIO_SECURE=false

# Neo4j（块 B 起启用）
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4jpassword
NEO4J_DATABASE=neo4j
```

### 8.4 连接管理生命周期

```
应用启动（startup）:
  ConnectionManager.startup()
    ├─ PostgreSQLConnector.connect()     # enabled=true  → 建立连接池
    ├─ RedisConnector                     # enabled=false → 跳过（registered only）
    ├─ MinIOConnector                     # enabled=false → 跳过
    └─ Neo4jConnector                     # enabled=false → 跳过

后续块启用某服务:
  块 B 启用 Redis 和 Neo4j:
    manager.get("redis").enabled = True
    manager.get("neo4j").enabled = True
    manager.get("redis").connect()
    manager.get("neo4j").connect()

应用关闭（shutdown）:
  ConnectionManager.shutdown()
    ├─ Neo4jConnector.disconnect()       # 先断知识图谱
    ├─ MinIOConnector.disconnect()       # 再断对象存储
    ├─ RedisConnector.disconnect()       # 再断缓存
    └─ PostgreSQLConnector.disconnect()  # 最后断数据库
```

### 8.5 健康状况

```python
@dataclass
class ConnHealth:
    name: str
    connected: bool
    enabled: bool
    latency_ms: float | None
    error: str | None
    metadata: dict = {}

# GET /api/v1/health 的 connections 部分自动聚合所有 ConnHealth
```

### 8.6 在本块的启用范围

| 服务 | 块 A 状态 | 注册 | 连接 | 说明 |
|------|----------|------|------|------|
| PostgreSQL | ✅ 启用 | ✅ | ✅ | 主数据库，ORM + 审计日志 |
| Redis | ⏸️ 预留 | ✅ | ❌ | 语义缓存/队列/会话，块 B 启用 |
| MinIO | ⏸️ 预留 | ✅ | ❌ | 对象存储，块 D 启用 |
| Neo4j | ⏸️ 预留 | ✅ | ❌ | 知识图谱，块 B 启用 |

---

## 9. 模块联通（输入/输出接口）

### 本块对外输出

```
输出 → 块 B（知识层）:
  - ConnectionManager（外服连接统一入口）— 供块 B 启用 Redis/Neo4j 连接
  - PostgreSQLConnector（数据库 Session 工厂）
  - Auth 中间件依赖 (app/auth/deps.py)
  - Workspace 上下文 (租户隔离)
  - LLM Gateway (app/llm_gateway/) — 所有 LLM 调用必经
  - ModelConfigManager — Embedding/Rerank/LLM 配置统一获取
  - 数据脱敏引擎 (app/security/data_masking.py) — 文档进 LLM 前先脱敏

输出 → 块 C（Agent 流水线）:
  - ConnectionManager（外服连接统一入口）
  - contracts/interfaces.py 所有接口定义
  - contracts/models.py 所有数据模型（含模型配置数据模型）
  - LLM Gateway — 4 个 Agent Layer 都通过 Gateway 调 LLM
  - ModelConfigManager — 所有 Agent Layer 通过它获取模型配置，支持 API 动态切换
  - 数据脱敏引擎 — 所有 PRD 内容进分析前先脱敏

输出 → 块 D（全链路串联）:
  - ConnectionManager（外服连接统一入口，块 D 启用 MinIO）
  - FastAPI 应用实例 (app/main.py)
  - 路由注册模式（含 /api/v1/model-config 路由）
  - UUID 审计日志 (app/security/audit_logger.py) — 每个请求自动记审计
  - ModelConfigManager 运行时状态 — 支持运维人员通过 API 动态调整模型配

输出 → 块 E（企业功能）:
  - ConnectionManager（外服连接统一入口）
  - users / workspaces 数据模型（会话历史/文档管理继承自这些表）
  - Auth 中间件（权限检查复用）
  - LLM Gateway 核心（块 E 在其上叠加预算控制和 LangFuse 集成）
  - ModelConfigManager（块 E 在其上叠加租户级模型配置覆盖）
```

### 本块对外输入

```
输入 ← 块 B: 无（块 B 依赖块 A）
输入 ← 块 C: 无
输入 ← 块 D: 无
输入 ← 块 E: 无
```

---

## 10. 完整链路

```
LLM 调用链路（所有后续块共享）:
  任意 Agent Node 调用 gateway.complete(prompt, task_type, workspace_id)
    → 模型配置中心解析: ModelConfigManager.resolve_model(task_type)
      → Router 查 routing_rules["analysis.requirement"] → {type: llm, provider: deepseek}
      → ModelConfigManager.merge_config("llm", "deepseek")
        ├─ 运行时内存态（API 注入，最高优先级）
        ├─ 环境变量 MODEL_CONFIG__LLM__DEEPSEEK__*
        └─ 默认值兜底
      → 返回完整 ModelConfig（含 api_key, base_url, default_model）
    → Provider 用返回的 config 初始化客户端
    → 数据脱敏引擎 (data_masking.py) 自动脱敏 prompt 中的敏感信息
    → 语义缓存 (cache.py) 查找是否命中 → 命中直接返回
    → Provider 抽象层 (provider.py) 调用实际 LLM
    → 成本追踪 (cost_tracker.py) 记录 input_tokens/output_tokens/cost
    → 审计日志 (audit_logger.py) 记录本次 LLM 调用
    → 返回 LLMResponse

  路由示例（由 ModelConfigManager 管理，支持 API 动态修改）:
    "analysis.requirement" → type=llm,  provider=deepseek, model=deepseek-chat
    "analysis.constraint"  → type=llm,  provider=deepseek, model=deepseek-chat
    "planning.architecture" → type=llm,  provider=deepseek, model=deepseek-chat
    "evaluation.scoring"   → type=judge, provider=openai,   model=gpt-4o-mini
    "embedding"            → type=embedding, provider=openai, model=text-embedding-3-small
    "rerank"               → type=rerank, provider=cohere,   model=rerank-english-v3.0

启动流程:
  uvicorn app.api.main:app
    → 加载配置 (app/core/config.py)
    → 初始化 ConnectionManager（注册 PostgreSQL/Redis/MinIO/Neo4j 连接器）
      → ConnectionManager.startup()
        ├─ PostgreSQLConnector.connect()      # 块 A 启用
        ├─ RedisConnector                     # 块 A: 跳过（lazy init）
        ├─ MinIOConnector                     # 块 A: 跳过（lazy init）
        └─ Neo4jConnector                     # 块 A: 跳过（lazy init）
    → 初始化 ModelConfigManager（从 Settings 读取环境变量/默认值）
    → 初始化 LLM Gateway（传入 ModelConfigManager）
      → ProviderFactory 注册所有供应商
      → Router 加载路由规则
      → CostTracker 初始化
      → Cache 初始化
    → 初始化数据脱敏引擎 (app/security/)
    → 注册中间件 (app/auth/middleware.py)
    → 注册路由（含 model_config CRUD 路由）
    → 等待请求

请求处理流程（以创建 workspace 为例）:
  POST /api/v1/workspaces
    → Auth 中间件解析 JWT → 提取 user_id + org_id
    → PermissionChecker 检查 workspace:create 权限
    → 审计日志记录操作 (audit_logger.py)
    → WorkspaceService.create()
      → 写入 workspaces 表
      → 创建者自动成为管理员 (team_members)
    → 返回 workspace 信息 + 201

健康检查:
  GET /api/v1/health
    → ConnectionManager.health_check()  # 检查所有已注册连接的状态
      ├─ postgres: connected / disconnected
      ├─ redis: connected / skipped (lazy)
      ├─ minio: connected / skipped (lazy)
      └─ neo4j: connected / skipped (lazy)
    → 检查 LLM Gateway 可用性
    → 检查 ModelConfigManager 关键模型配置是否就绪
    → 返回 {"status": "ok", "connections": {"postgres": "connected", "redis": "skipped",
            "minio": "skipped", "neo4j": "skipped"},
            "gateway": "ready",
            "model_config": {"llm": true, "embedding": true, "judge": true},
            "version": "0.1.0"}
```

---

## 11. 测试用例

### 11.1 连接管理测试

```python
# tests/unit/test_connections.py
async def test_connection_manager_startup_shutdown():
    """验证 ConnectionManager 启动/关闭生命周期。"""
    ...

async def test_postgresql_connector_connect():
    """验证 PostgreSQL 连接池正常建立。"""
    ...

async def test_lazy_init_connector():
    """验证预留服务（Redis/MinIO/Neo4j）注册但不连接。"""
    ...

async def test_connection_health_check():
    """验证健康检查正确反映各连接状态。"""
    ...

async def test_graceful_shutdown_order():
    """验证关闭顺序：Neo4j→MinIO→Redis→PostgreSQL。"""
    ...
```

### 11.2 技术栈合规测试

```python
# tests/test_tech_stack_compliance.py
def test_no_langchain_import():
    """检测是否有 langchain 被引入。"""
    ...

def test_required_packages_installed():
    """检测必须的包（llama-index, fastapi, sqlalchemy 等）是否在 requirements.txt。"""
    ...

def test_forbidden_packages_not_installed():
    """检测禁止的包（chromadb, flask 等）不在 requirements.txt。"""
    ...
```

### 11.3 Auth 流程测试

```python
# tests/integration/test_auth_flow.py
async def test_register_login_flow():
    """完整用户注册→登录→访问受保护资源→刷新→登出。"""
    ...

async def test_token_expiry():
    """验证 access_token 15分钟过期，refresh_token 7天过期。"""
    ...

async def test_permission_check():
    """验证无权限用户访问受限资源返回 403。"""
    ...

async def test_workspace_isolation():
    """验证 A 工作空间的用户不能访问 B 工作空间的资源。"""
    ...
```

### 11.4 模型配置中心测试

```python
# tests/unit/test_model_config.py

async def test_config_priority_env_over_default():
    """验证环境变量优先级高于默认值。"""
    manager = ModelConfigManager(settings_with_env={"llm.deekseek.api_key": "sk-env"})
    config = manager.get_config(ModelType.LLM, "deepseek")
    assert config.api_key == "sk-env"  # 环境变量覆盖默认值

async def test_config_priority_runtime_over_env():
    """验证 API 运行时注入优先级高于环境变量。"""
    manager = ModelConfigManager(settings_with_env={"llm.deekseek.api_key": "sk-env"})
    manager.update_config(ModelType.LLM, "deepseek", {"api_key": "sk-runtime"})
    config = manager.get_config(ModelType.LLM, "deepseek")
    assert config.api_key == "sk-runtime"  # 运行时覆盖环境变量

async def test_routing_rule_resolution():
    """验证 task_type → 完整 ModelConfig 解析。"""
    manager = ModelConfigManager(...)
    config, model_name = manager.resolve_model("analysis.requirement")
    assert config.provider == "deepseek"
    assert config.default_model == "deepseek-chat"

async def test_dynamic_routing_update():
    """验证运行时修改路由规则后立即生效。"""
    manager = ModelConfigManager(...)
    manager.update_routing_rule("analysis.requirement",
                                 RoutingRule(type=ModelType.LLM, provider="openai"))
    config, model_name = manager.resolve_model("analysis.requirement")
    assert config.provider == "openai"  # 路由已切换

async def test_masked_api_key():
    """验证 API Key 掩码函数正确。"""
    config = ModelConfig(api_key="sk-abcdef1234567890")
    assert config.masked_api_key() == "sk-a****7890"
    assert "sk-abcdef" not in config.masked_api_key()

async def test_config_merge_partial_update():
    """验证部分更新时未提供的字段保留原值。"""
    manager = ModelConfigManager(...)
    original = manager.get_config(ModelType.LLM, "deepseek")
    manager.update_config(ModelType.LLM, "deepseek", {"api_key": "sk-new"})
    updated = manager.get_config(ModelType.LLM, "deepseek")
    assert updated.api_key == "sk-new"       # 更新的字段变了
    assert updated.base_url == original.base_url  # 未提供的字段保留

async def test_reset_runtime_config():
    """验证清除运行时配置后恢复为环境变量值。"""
    manager = ModelConfigManager(...)
    manager.update_config(ModelType.LLM, "deepseek", {"api_key": "sk-runtime"})
    manager.reset_to_env()
    config = manager.get_config(ModelType.LLM, "deepseek")
    assert config.api_key != "sk-runtime"  # 已恢复
```

### 11.5 LLM Gateway 测试（集成 ModelConfigManager）

```python
# tests/unit/test_llm_gateway.py

async def test_gateway_config_resolution():
    """验证 Gateway 通过 ModelConfigManager 解析模型配置。"""
    manager = ModelConfigManager()
    config, model = manager.resolve_model("analysis.requirement")
    assert config.provider == "deepseek"
    assert model == "deepseek-chat"

async def test_gateway_dynamic_config_takes_effect():
    """验证运行时修改配置后，Gateway 后续调用使用新配置。"""
    manager = ModelConfigManager()
    manager.update_config(ModelType.LLM, "deepseek",
                          {"base_url": "https://custom.deepseek.com/v1"})
    config, model = manager.resolve_model("analysis.requirement")
    assert "custom.deepseek.com" in config.base_url

async def test_gateway_tracks_cost():
    """验证成本追踪记录 token+cost。"""
    result = await gateway.complete("Hello", "test", "ws-1")
    assert result.cost > 0
    assert result.input_tokens > 0
    assert result.model is not None

async def test_semantic_cache_hit():
    """验证语义缓存：相同查询第二次命中缓存。"""
    r1 = await gateway.complete("What is PRD?", "test", "ws-1")
    r2 = await gateway.complete("What is PRD?", "test", "ws-1")
    assert r2.cached == True

async def test_provider_fallback():
    """验证主模型失败时自动降级到备用模型。"""
    result = await gateway.complete("test", "test", "ws-1",
                                     force_fallback=True)
    assert result.model == "gpt-4o-mini"  # 降级到 fallback
```

### 11.6 模型配置 API 集成测试

```python
# tests/integration/test_model_config_api.py

async def test_get_all_configs():
    """GET /api/v1/model-config 返回所有模型配置，API Key 被掩码。"""
    response = await client.get("/api/v1/model-config")
    assert response.status_code == 200
    data = response.json()
    assert "llm" in data
    assert "embedding" in data
    assert "rerank" in data
    assert "judge" in data
    # 验证 API Key 被掩码
    assert "****" in data["llm"]["deepseek"]["api_key"]
    assert "sk-" not in data["llm"]["deepseek"]["api_key"]

async def test_update_config():
    """PUT /api/v1/model-config 修改配置后后续查询返回新值。"""
    response = await client.put("/api/v1/model-config", json={
        "type": "llm",
        "provider": "deepseek",
        "base_url": "https://custom.deepseek.com/v1",
    })
    assert response.status_code == 200
    # 验证已生效
    get_resp = await client.get("/api/v1/model-config?type=llm&provider=deepseek")
    assert "custom.deepseek.com" in get_resp.json()["base_url"]

async def test_update_routing_rule():
    """PUT /api/v1/model-config/routing 修改路由规则后立即生效。"""
    response = await client.put("/api/v1/model-config/routing", json={
        "task_type": "analysis.requirement",
        "provider": "openai",
        "model": "gpt-4o",
    })
    assert response.status_code == 200

async def test_reset_runtime_config():
    """DELETE /api/v1/model-config/runtime 清除运行时配置。"""
    await client.put("/api/v1/model-config", json={
        "type": "llm", "provider": "deepseek",
        "api_key": "sk-temp",
    })
    resp = await client.delete("/api/v1/model-config/runtime")
    assert resp.status_code == 200
```

### 11.7 数据脱敏测试

```python
# tests/unit/test_data_masking.py
def test_mask_api_key():
    """验证 API Key 被正确脱敏。"""
    engine = DataMaskingEngine()
    result = engine.mask("sk-abc123def456")
    assert "[MASKED_API_KEY]" in result
    assert "sk-" not in result

def test_mask_email():
    """验证邮箱被脱敏。"""
    engine = DataMaskingEngine()
    result = engine.mask("联系邮箱: user@example.com")
    assert "[MASKED_EMAIL]" in result

def test_mask_by_level():
    """验证不同安全等级脱敏范围不同。"""
    engine = DataMaskingEngine()
    text = "密码: pass123, 邮箱: a@b.com, 公网IP: 8.8.8.8"
    l1 = engine.mask(text, level="L1")
    l2 = engine.mask(text, level="L2")
    assert "[MASKED_PASSWORD]" not in l1  # L1 不脱敏密码
    assert "[MASKED_PASSWORD]" in l2      # L2 脱敏密码
```

### 11.8 审计日志测试

```python
# tests/unit/test_audit_logger.py
async def test_audit_log_hash_chain():
    """验证审计日志哈希链连续性。"""
    log1 = await write_audit_log({"action": "create", "resource": "workspace"})
    log2 = await write_audit_log({"action": "delete", "resource": "workspace"})
    assert log2.previous_hash == log1.current_hash
    assert log2.current_hash != log1.current_hash

async def test_audit_log_tamper_detection():
    """验证篡改审计日志可被检测。"""
    logs = await get_audit_logs()
    assert verify_hash_chain(logs) == True  # 未篡改
    logs[1].detail = {"action": "modified"}
    assert verify_hash_chain(logs) == False  # 检测到篡改
```

### 11.9 数据模型测试

```python
# tests/unit/test_models.py
def test_user_model_fields():
    """验证 User 模型所有字段类型正确。"""
    ...

def test_workspace_unique_constraint():
    """验证同一 organization 下 slug 唯一。"""
    ...

def test_team_member_relationship():
    """验证 User → Workspace 多对多关系通过 team_members 正确建立。"""
    ...
```

### 11.10 注释完整性测试

```python
# tests/test_lint.py
def test_all_functions_have_docstrings():
    """扫描 app/ 下所有 .py 文件，检查每个 public 函数是否有 docstring。"""
    ...

def test_no_todo_or_fixme():
    """扫描 app/ 下所有 .py 文件，检查无 TODO/FIXME/NotImplementedError。"""
    ...
```

---

## 12. 验收标准

### 必须满足

```bash
# 1. 技术栈合规（不允许有任何违规依赖）
pytest tests/test_tech_stack_compliance.py -v
# 输出: 3 passed

# 2. 类型检查（严格模式零错误）
mypy app/ --strict --ignore-missing-imports
# 输出: Success: no issues found

# 3. 代码风格（零错误）
ruff check app/ tests/
# 输出: All checks passed!

# 4. CI/CD 合规（检查 GitHub Actions 配置）
test -f .github/workflows/ci.yml && test -f .github/workflows/deploy-prod.yml && test -f .github/workflows/backup.yml
# 输出: 3 个文件都存在
grep -q "ruff" .github/workflows/ci.yml && grep -q "mypy" .github/workflows/ci.yml
# 输出: 两个检查都通过（退出码 0）

# 5. 全部测试通过
pytest tests/ -v --tb=short
# 输出: 100% passed, 0 skipped

# 6. 无 TODO 残留
grep -rn "TODO\|FIXME\|NotImplementedError\|^\s*pass\s*$" app/ --include="*.py"
# 如果没有输出（空）则通过；如果有则检查是否合理

# 6. 无空测试函数
grep -rn "def test.*:\s*$\|def test.*:\s*\n\s*pass\|\s*assert True" tests/ --include="*.py"
# 如果没有输出（空）则通过
```

### 联通性测试

```bash
# 启动所有容器
docker compose up -d

# ── 基础设施连接管理单元测试 ──
pytest tests/unit/test_connections.py -v
# 期望: ConnectionManager 启动/关闭/健康检查/lazy init 全部通过

# ── PostgreSQL 连接验证（块 A 启用）──
pytest tests/integration/test_db_connection.py -v
# 期望输出: "PostgreSQL 16 + pgvector 0.7 连接成功"

# ── Redis 连接验证（块 B 起启用，块 A 验证注册和健康检查接口）──
python -c "
from app.core.connections import connection_manager
conn = connection_manager.get('redis')
assert conn is not None, 'Redis 连接器未注册'
assert conn.enabled == False, '块 A 中 Redis 应为 lazy init'
health = conn.health()
assert health.name == 'redis'
print(f'Redis 连接器状态: name={health.name}, enabled={health.enabled}, connected={health.connected}')
"

# ── MinIO 连接验证（块 D 起启用，块 A 验证注册和健康检查接口）──
python -c "
from app.core.connections import connection_manager
conn = connection_manager.get('minio')
assert conn is not None, 'MinIO 连接器未注册'
assert conn.enabled == False, '块 A 中 MinIO 应为 lazy init'
health = conn.health()
print(f'MinIO 连接器状态: name={health.name}, enabled={health.enabled}, connected={health.connected}')
"

# ── Neo4j 连接验证（块 B 起启用，块 A 验证注册和健康检查接口）──
python -c "
from app.core.connections import connection_manager
conn = connection_manager.get('neo4j')
assert conn is not None, 'Neo4j 连接器未注册'
assert conn.enabled == False, '块 A 中 Neo4j 应为 lazy init'
health = conn.health()
print(f'Neo4j 连接器状态: name={health.name}, enabled={health.enabled}, connected={health.connected}')
"

# ── Auth 全流程验证 ──
pytest tests/integration/test_auth_flow.py -v
# 期望输出: "register → login → access → refresh → logout 全部通过"

# 验证 LLM Gateway 可用
pytest tests/integration/test_llm_gateway.py -v
# 期望: 模型配置解析正确 + 成本可追踪 + 缓存命中 + Provider 降级

# 验证模型配置中心单元测试
pytest tests/unit/test_model_config.py -v
# 期望: 三级优先级 + 路由解析 + 动态更新 + 部分合并 + Key 掩码 + 重置 全部通过

# 验证模型配置 API
pytest tests/integration/test_model_config_api.py -v
# 期望: GET（配置返回+Key掩码）/ PUT（配置更新）/ 路由更新 / 重置 全部通过

# 验证数据脱敏
pytest tests/unit/test_data_masking.py -v
# 期望: 各类型敏感数据（API Key/邮箱/密码/IP）被正确脱敏

# 验证审计日志
pytest tests/unit/test_audit_logger.py -v
# 期望: 哈希链连续 + 篡改可检测

# 验证 API 存活且返回 OpenAPI 文档
uvicorn app.api.main:app --port 8000 &
curl -s http://localhost:8000/docs | grep -q "openapi"
# 期望: 返回 200，包含 OpenAPI JSON

# 验证 Workspace CRUD
pytest tests/integration/test_workspace_api.py -v
# 期望输出: "workspace CRUD 全部通过"

# 验证模型配置覆盖所有涉及模型调用的模块
pytest tests/unit/test_model_config.py -k "test_routing" -v
# 期望: 所有模型类型（LLM/Embedding/Rerank/Judge/Vision）的路由均正确解析
```

### 完成后状态

```
✅ 项目可 clone → pip install → docker compose up → 启动
✅ 数据库可连接，模型已迁移
✅ 注册/登录/权限检查可用
✅ 多租户隔离生效
✅ 模型配置中心可用（三级优先级 + API 动态注入 + 环境变量兜底）
✅ LLM Gateway 可用（ModelConfigManager 配置解析 + 成本追踪 + 缓存 + 降级）
✅ 所有模型类型（LLM/Embedding/Rerank/Judge/Vision）均统一从 ModelConfigManager 获取配置
✅ ConnectionManager 就绪，管理 PostgreSQL/Redis/MinIO/Neo4j 统一连接生命周期
✅ PostgreSQL 块 A 直接启用，Redis/MinIO/Neo4j 预注册（lazy init，后续块启用）
✅ 健康检查覆盖全部基础设施服务连接状态
✅ 数据脱敏引擎就绪（API Key/Token/密码/邮箱自动脱敏）
✅ 审计日志哈希链可用（篡改可检测）
✅ CI/CD 流水线就绪（PR 自动跑 lint+type-check+test + 手动生产部署 + 定时备份）
✅ 所有 Layer 的 Contract 接口已定义
✅ 质量门禁全部就绪（违规会红）
✅ 可进入块 B 开发
```
