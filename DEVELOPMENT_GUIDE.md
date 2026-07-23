# 开发铁律（必读）

> 这个文件的目的是防止"AI 生成了几千行代码，但跑不起来"的问题。
> **Vibe Coding 模式请额外阅读 [VIBE_CODING_RULES.md](VIBE_CODING_RULES.md)**。
> **每个 Session 开始前，去 [docs/phase-prompts.md](docs/phase-prompts.md) 复制对应 Phase 的 Prompt**。

---

## 铁律零：技术栈锁定

**LlamaIndex 是唯一允许的 RAG 框架，禁止引入 LangChain 任何包。**

详细禁止/必须清单见 [VIBE_CODING_RULES.md 第一章](VIBE_CODING_RULES.md#一技术栈强制约束)。

```bash
# 每次生成后第一件事：检查有没有引入违规依赖
grep -c "langchain" requirements.txt || echo "0"
# 输出必须为 0
```

---

## 铁律一：每次 Session 只做一个块

```
块 A → 块 B → 块 C → 块 D → 块 E
```

各块定义见 [docs/phase-prompts.md](docs/phase-prompts.md)。
不允许跳块。块 N 必须在块 N-1 的代码基础上做，且块 N-1 的集成测试必须全绿。

---

## 铁律二：外部依赖一个一个加

每个 Phase 的文档顶部都标明了**新增的外部依赖数量**。

加入新服务的步骤：

```bash
# 1. 先 docker compose up 新服务
docker compose up -d <新服务>

# 2. 写一个独立的连接测试脚本
python -c "
import psycopg2  # 或其他驱动
conn = psycopg2.connect(...)
print('连接成功')
"

# 3. 这个脚本跑通后，再写业务代码
# 4. 业务代码写完后，运行集成测试
pytest tests/integration/test_pipeline.py -v
```

**如果第 2 步跑不通，不要写第 3 步的代码。** 不存在"先写代码后面再调试连接"这回事。

---

## 铁律三：Contracts 不可变

`contracts/` 目录下的所有文件在 Phase 0 定义后**不允许修改**。

如果发现必须改：
1. 在当前 Phase 文档中注明"需修改 Contracts"
2. 一次性改完 `contracts/` 所有受影响的文件
3. 运行 `pytest tests/test_contracts.py` 确保所有模型可序列化
4. 通知所有使用该 contract 的 session 同步更新

---

## 铁律四：每个 Phase 结束时必须有一个通过的端到端测试

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

每次 session 结束时运行：
```bash
pytest tests/ -v
# 必须全部通过，不能有 skipped / xfailed
```

---

## 铁律五：不存在"下一阶段再修"的 TODO

写代码时如果遇到：
- ❌ `# TODO: 后面接真实数据库`
- ❌ `# FIXME: 这里需要错误处理`
- ❌ `raise NotImplementedError`

**在这个 Phase 内必须处理完。** 如果某个功能确实不属于当前 Phase，就不要写它的桩代码——Phase 0 里的 `knowledge.py` 返回空字符串是可以的，因为那是 Phase 0 的明确设计。但 Phase 2 里就不能再返回空了，必须接入向量检索。

---

## 铁律六：改接口先改测试

需要修改某个 Layer 的接口签名时，顺序是：

```
1. 改 contracts/interfaces.py
2. 改 tests/ 中对应的 Mock
3. 运行测试（此时应该红）
4. 改实现代码
5. 运行测试（此时应该绿）
```

不允许先改实现再回来改测试。

---

---

## 铁律七：技术栈由测试强制，不靠 AI 自觉

AI 倾向于用自己熟悉的库（LangChain）替代文档指定的库（LlamaIndex）。
用测试卡死，不依赖 AI 的"自觉"。

### 7.1 `tech-stack.yml` 是唯一真相来源

```
prd2tsd-agents/
└── tech-stack.yml        # ← 声明所有允许/禁止的库
```

### 7.2 每次 Session 必须运行技术栈合规测试

```bash
pytest tests/test_tech_stack_compliance.py -v
# 如果导入了黑名单库（如 langchain），测试红 → 不允许合并
```

### 7.3 添加新依赖的流程

```bash
# 1. 先确认该库与 tech-stack.yml 不冲突
# 2. 添加到 requirements.txt
# 3. 如果它是核心依赖，更新 tech-stack.yml 的 allowed 列表
# 4. 运行技术栈合规测试
pytest tests/test_tech_stack_compliance.py -v
```

---

## 铁律八：质量门禁从 Phase 0 第一天就启用

### 8.1 Phase 0 必须包含的质量基础设施

```
prd2tsd-agents/
├── pyproject.toml               # ruff(flake8替代) + mypy + pytest 配置
├── .github/workflows/ci.yml     # PR 自动跑 lint + type-check + test
└── tests/
    ├── conftest.py
    ├── test_tech_stack_compliance.py  # 技术栈合规（铁律七）
    ├── test_lint.py                   # 注释完整性 + ruff 零错误
    └── test_e2e.py                    # 端到端测试
```

### 8.2 每个函数/类必须有 docstring

```python
# ✅ 合格的注释（Google 风格）
def retrieve(self, query: str, top_k: int = 10) -> list[str]:
    """检索相关知识上下文。
    
    Args:
        query: 查询文本。
        top_k: 返回结果数。
        
    Returns:
        相关文本片段列表。
    """
    ...

# ❌ 不合格
def retrieve(self, query: str, top_k: int = 10):
    return []
```

### 8.3 每次 Session 结束时必须通过的检查

```bash
# 1. ruff 检查（零错误）
ruff check app/ --exit-zero

# 2. mypy 类型检查（零错误）
mypy app/

# 3. 所有测试 100% 通过（不允许 skipped）
pytest tests/ -v --tb=short

# 4. 每条命令必须输出明确成功信息
# 不允许出现 "429 skipped" 或 "warnings ignored"
```

---

## 各块快速参考

每个块的完整需求文档在 `docs/` 目录下，可直接喂给 AI。

| 块 | 需求文档 | 天数 | 新增容器 | 关键联通性测试 |
|----|---------|------|---------|--------------|
| A | [`docs/block-A-infrastructure.md`](docs/block-A-infrastructure.md) | 3-5 | postgres | `test_db_connection.py`, `test_auth_flow.py` |
| B | [`docs/block-B-knowledge-layer.md`](docs/block-B-knowledge-layer.md) | 3-5 | neo4j | `test_kg_build.py`, `test_local_search.py`, `test_global_search.py` |
| C | [`docs/block-C-agent-pipeline.md`](docs/block-C-agent-pipeline.md) | 5-7 | 0 | 4 层独立测试 |
| D | [`docs/block-D-orchestration.md`](docs/block-D-orchestration.md) | 3-5 | 0 | `test_pipeline.py`, `test_full_flow.py` |
| E | [`docs/block-E-enterprise.md`](docs/block-E-enterprise.md) | 3-5 | jaeger, prom, minio | 各功能独立测试 + 回归 |
