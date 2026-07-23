# Vibe Coding 技术约束宪章

> Vibe Coding 模式 = AI Agent 写全部代码，人只做 Prompt + Review + 集成测试。
> 这份文件是**所有生成 session 必须遵守的硬性约束**。违反的代码不允许合入。

---

## 一、技术栈强制约束

### 1.1 必须使用（严格锁定）

```yaml
llm_framework:
  - "llama-index>=0.11.0"           # 知识图谱索引、检索、RAG 全部基于 LlamaIndex
  - "llama-index-graph-stores-neo4j"
  - "llama-index-vector-stores-postgres"

agent_framework:
  - "langgraph>=0.2.0"              # Agent 编排

embedding:
  - "BAAI/bge-large-zh-v1.5"       # 中文 Embedding（1024维）

llm_client:
  - "openai>=1.0"                   # OpenAI SDK（兼容 DeepSeek API）

vector_db:
  - "pgvector"                      # PostgreSQL 向量扩展

graph_db:
  - "neo4j>=5.0"                    # 图数据库 Python Driver

web_framework:
  - "fastapi>=0.110"
  - "uvicorn"

test_framework:
  - "pytest>=8.0"
  - "pytest-asyncio"
  - "ruff"                          # 替代 flake8（更快）
  - "mypy"                          # 类型检查
```

### 1.2 禁止引入

```yaml
forbidden:
  - "langchain"                     # 整个 langchain 生态禁止引入
  - "langchain-community"
  - "langchain-openai"
  - "chromadb"                      # 已指定 PGVector，不用其他向量库
  - "redis"                         # Phase 5 之前不用 Redis
  - "celery"                        # Phase 5 之前不用 Celery
  - "sqlite"                        # 生产环境不用 SQLite
```

### 1.3 违反后果

代码审查时发现引入禁止库 → 整个 PR 打回，不合并。**不允许"先引入后面再替换"**。

---

## 二、代码质量标准

### 2.1 必须通过的检查

```bash
# 1. 类型检查（严格模式）
mypy app/ --strict --ignore-missing-imports

# 2. 代码风格
ruff check app/ tests/

# 3. 测试
pytest tests/ -v --tb=short
# 结果: 100% passed, 0 skipped, 0 xfailed

# 4. 端到端
pytest tests/integration/test_pipeline.py -v
```

### 2.2 每个函数的要求

```python
# ✅ 必须有 type hint（参数 + 返回值）
# ✅ 必须有 docstring（描述功能 + 参数 + 返回值 + 异常）
# ✅ 函数不超过 50 行（超过必须拆）
# ✅ 不允许全局变量（除了配置常量）

def retrieve(self, query: str, top_k: int = 10) -> list[ScoredDoc]:
    """从向量库检索相关文档块。
    
    Args:
        query: 用户查询文本
        top_k: 返回结果数，默认 10
        
    Returns:
        list[ScoredDoc]: 按相关性降序排列的文档块列表
        
    Raises:
        ConnectionError: 向量库连接失败时抛出
    """
    ...
```

### 2.3 禁止模式

```python
# ❌ 禁止
# TODO: 后面再实现
# FIXME: 需要修复
# pass
# raise NotImplementedError
# (...)  # 省略号占位
# type: ignore[xxx]  # 除非有明确理由注释

# ✅ 允许（Phase 边界明确标记）
# VIBE_DEFER(Phase 3): 此处在 Phase 3 接入 Neo4j，当前返回空列表
```

---

## 三、测试标准

### 3.1 测试覆盖要求

| 层级 | 要求 |
|------|------|
| 每个 public 函数 | ≥ 1 个单元测试 |
| 每个 API 端点 | ≥ 1 个集成测试 |
| 每个 Layer | ≥ 1 个端到端测试（含 Mock） |
| 全链路 | 1 个完整端到端测试 |

### 3.2 测试禁止事项

```python
# ❌ 禁止
def test_something():
    pass  # 空测试

def test_something():
    assert True  # 无意义测试

def test_something():
    # TODO: 写测试
    ...

# ✅ 正确
async def test_analysis_extracts_requirements():
    """验证 Analysis Layer 能从 PRD 中正确提取需求"""
    prd = "# 项目名称：电商平台\n## 功能需求\n1. 用户登录"
    result = await analysis_layer.analyze(prd)
    assert len(result.requirements) > 0
    assert result.requirements[0].type == "functional"
```

---

## 四、生成后检查清单

每个 Vibe Coding session 结束时，**必须依次执行以下检查**，全部通过才算完成：

```bash
# 第 1 关：依赖检查
grep -c "langchain" requirements.txt
# 输出必须为 0

grep "llama-index" requirements.txt
# 输出必须非空

# 第 2 关：类型检查
mypy app/ --strict --ignore-missing-imports
# 必须 0 error

# 第 3 关：代码风格
ruff check app/ tests/
# 必须 0 error

# 第 4 关：单元测试
pytest tests/unit/ -v --tb=short
# 必须 100% passed

# 第 5 关：集成测试
pytest tests/integration/ -v --tb=short
# 必须 100% passed

# 第 6 关：联通性测试
# 每个 Session 有自己独特的联通性测试（见 docs/phase-prompts.md）
pytest tests/integration/ -v --tb=short
# 必须 100% passed

# 第 7 关：无 TODO/FIXME 残留
grep -rn "TODO\|FIXME\|NotImplementedError" app/ --include="*.py" || echo "CLEAN"
# 输出必须包含 "CLEAN"
```

**任一关不过 → 这个 session 的产出视为无效，不提交。**

---

## 五、Session 启动模板

每次开始新的 Vibe Coding session 时，打开对应块的独立需求文档（共 5 份，在 `docs/` 目录下），
把整份文档作为首条消息喂给 AI，不要手写。
如果找不到对应块，再使用以下通用模板：

```
你正在开发 PRD2TechSpec 项目 {块 名}（例如"块 A：基础设施与质量底座"）。
技术约束见 VIBE_CODING_RULES.md，详细范围见 docs/phase-prompts.md，必须严格遵守。

关键约束：
1. 禁止引入 langchain 任何包，必须使用 llama-index
2. 所有函数必须有 type hint 和 docstring
3. 不允许 # TODO / pass / raise NotImplementedError
4. 测试不允许空函数或 assert True
5. 生成结束后必须能通过 ruff check 和 mypy --strict
6. 本块新增外部依赖: {N} 个容器

当前块范围：
{一句话描述此块做什么、不做什么}
```
