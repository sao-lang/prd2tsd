# PRD2TSD — PRD to Technical Specification Document Agent System

> 基于 LLM Agent 的 PRD（产品需求文档）到 TSD（技术方案设计文档）自动转换系统。

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                       用户交互层                              │
│          FastAPI (REST API)        CLI (开发调试)             │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                     Agent Orchestrator                       │
│                                                              │
│   Knowledge Layer  →  Analysis Layer  →  Planning Layer      │
│   (知识图谱+检索)      (需求分析)         (架构规划)          │
│         ↓                   ↓                  ↓             │
│                    Generation Layer                          │
│                    (文档生成)                                 │
│                                                              │
│                    Evaluation System                         │
│                    (质量评测)                                 │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                       基础设施层                              │
│  ┌─────────┐  ┌──────────────┐  ┌───────┐  ┌────────┐      │
│  │ Neo4j   │  │ PostgreSQL+  │  │ Redis │  │ MinIO  │      │
│  │ 图数据库 │  │ PGVector     │  │ 缓存  │  │ 对象存储│      │
│  └─────────┘  └──────────────┘  └───────┘  └────────┘      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              LLM Gateway                              │    │
│  │  Provider/Router/CostTracker/Cache/ConfigManager      │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **Web 框架** | FastAPI + uvicorn | 异步 REST API |
| **ORM** | SQLAlchemy 2.0 + asyncpg | 异步 PostgreSQL 驱动 |
| **向量存储** | pgvector (PostgreSQL 扩展) | 1024 维向量 |
| **图数据库** | Neo4j 5.x | 知识图谱存储 |
| **缓存** | Redis 7.x | 会话/缓存/队列 |
| **对象存储** | MinIO | 文档/图片存储 |
| **LLM SDK** | OpenAI SDK | 兼容 DeepSeek API |
| **RAG 框架** | LlamaIndex 0.11+ | PropertyGraphIndex |
| **Embedding** | BAAI/bge-large-zh-v1.5 | 中文 Embedding |
| **Agent 编排** | LangGraph | StateGraph 工作流 |
| **配置** | pydantic-settings | 三级优先级配置 |
| **认证** | python-jose (JWT) + bcrypt | RBAC 权限模型 |
| **测试** | pytest + pytest-asyncio | 异步测试 |

## 项目结构

```
prd2tsd-agents/
├── app/
│   ├── main.py                     # FastAPI 应用入口
│   ├── core/                       # 基础设施
│   │   ├── config.py               # pydantic-settings 配置
│   │   ├── connections/            # 连接管理器（PostgreSQL/Redis/MinIO/Neo4j）
│   │   ├── llm.py                  # LLM 客户端
│   │   ├── logger.py               # 结构化日志
│   │   └── exceptions.py           # 自定义异常
│   ├── auth/                       # 认证授权
│   │   ├── token_manager.py        # JWT 签发/验证
│   │   ├── permissions.py          # RBAC 权限检查
│   │   ├── middleware.py           # Auth + 租户中间件
│   │   └── deps.py                 # FastAPI 依赖注入
│   ├── llm_gateway/                # LLM Gateway
│   │   ├── providers/              # Provider 抽象层
│   │   ├── router.py               # 模型路由
│   │   ├── cost_tracker.py         # 成本追踪
│   │   ├── cache.py                # 语义缓存
│   │   └── config_manager.py       # 模型配置管理
│   ├── knowledge_layer/            # 知识层（块 B）
│   │   ├── ingestion/              # 文档处理管线
│   │   ├── retrieval/              # 多路检索管线
│   │   ├── graph_store.py          # Neo4j CRUD
│   │   ├── vector_store.py         # PGVector 读写
│   │   └── pipeline.py             # 主入口
│   ├── models/                     # SQLAlchemy 数据模型
│   ├── security/                   # 数据安全
│   └── api/                        # API 路由
├── contracts/                      # 跨层接口定义
├── tests/                          # 测试
│   ├── unit/                       # 单元测试
│   └── integration/                # 集成测试
├── docs/                           # 设计文档
├── scripts/                        # 工具脚本
└── docker-compose.yml              # 容器编排
```

## 快速开始

### 前置条件

- Docker & Docker Compose
- Python ≥ 3.12
- 一个兼容 OpenAI API 的 LLM API Key（DeepSeek / OpenAI）

### 1. 启动基础设施

```bash
docker compose up -d
```

启动后 4 个容器：
- **PostgreSQL** (5432) — 业务数据 + PGVector
- **Neo4j** (7474/7687) — 知识图谱（Browser: http://localhost:7474）
- **Redis** (6379) — 缓存
- **MinIO** (9000/9001) — 对象存储

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 API Key：
# MODEL_CONFIG__LLM__DEEPSEEK__API_KEY=sk-your-key
```

### 3. 初始化数据库

```bash
# 创建 Python 虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 初始化数据库表
python scripts/init_db.py

# 运行 Alembic 迁移
alembic upgrade head
```

### 4. 启动 API 服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8012 --reload
```

### 5. 运行测试

```bash
# 全部单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# E2E 全链路测试（需服务运行中）
python scripts/e2e_test.py
```

## API 接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 | 否 |
| `POST` | `/api/v1/auth/register` | 用户注册 | 否 |
| `POST` | `/api/v1/auth/login` | 用户登录 | 否 |
| `POST` | `/api/v1/auth/refresh` | 刷新 Token | 否 |
| `GET` | `/api/v1/auth/me` | 当前用户信息 | 是 |
| `POST` | `/api/v1/workspaces` | 创建工作空间 | 是 |
| `GET` | `/api/v1/workspaces` | 列出工作空间 | 是 |
| `GET` | `/api/v1/workspaces/{id}` | 工作空间详情 | 是 |
| `PUT` | `/api/v1/workspaces/{id}` | 更新工作空间 | 是 |
| `DELETE` | `/api/v1/workspaces/{id}` | 归档工作空间 | 是 |
| `POST` | `/api/v1/workspaces/{id}/members` | 添加成员 | 是 |
| `DELETE` | `/api/v1/workspaces/{id}/members/{uid}` | 移除成员 | 是 |
| `GET` | `/api/v1/model-config` | 查询模型配置 | 否 |
| `PUT` | `/api/v1/model-config` | 更新模型配置 | 否 |
| `DELETE` | `/api/v1/model-config/runtime` | 重置运行时配置 | 否 |
| `PUT` | `/api/v1/model-config/routing` | 更新路由规则 | 否 |
| `POST` | `/api/v1/knowledge/build` | 上传文档构建知识图谱 | 是 |
| `POST` | `/api/v1/knowledge/search` | 知识图谱检索 | 是 |

## 知识层使用示例

### 构建知识图谱

```bash
# 上传 .md 文件
curl -X POST http://localhost:8012/api/v1/knowledge/build \
  -H "Authorization: Bearer <token>" \
  -F "file=@docs/sample.md"

# 从服务端文件路径构建
curl -X POST http://localhost:8012/api/v1/knowledge/build-from-path \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/doc.md"}'
```

### 检索知识图谱

```bash
curl -X POST "http://localhost:8012/api/v1/knowledge/search?query=用户服务用了什么技术栈&mode=hybrid&top_k=10" \
  -H "Authorization: Bearer <token>"
```

## 开发阶段

| 阶段 | 状态 | 说明 |
|------|------|------|
| **块 A** | ✅ 完成 | 基础设施、Auth、LLM Gateway、数据安全、CI/CD |
| **块 B** | ✅ 完成 | 知识图谱构建、多路检索、版本控制、老化策略 |
| **块 C** | ⏳ 待开始 | Agent 流水线（Knowledge/Analysis/Planning/Generation Layer） |
| **块 D** | ⏳ 待开始 | Agent Orchestrator + Evaluation System |
| **块 E** | ⏳ 待开始 | 企业功能（SSO/监控/多模态/Web UI） |

## 编码规范

- **Python ≥ 3.12**，类型注解必须完整
- **Ruff** 代码风格检查（`ruff check .`）
- **mypy** 类型检查（`mypy app/ --strict --ignore-missing-imports`）
- **pytest** 测试覆盖正常/边界/异常路径
- 每个函数 ≤ 50 行，每个文件 ≤ 300 行
- 禁止 `TODO` / `FIXME` / `pass` / `raise NotImplementedError`
- 禁止使用 LangChain 生态（使用 LlamaIndex）

## 许可证

MIT
