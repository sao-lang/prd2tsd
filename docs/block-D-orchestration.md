# 块 D：全链路串联 + API

> 关联总文档：`prd2tsd.md` §二 Agent Orchestrator、§9.2 API 接口完整列表、§2.3 Human-in-the-Loop
>
> **前置条件**：块 A + 块 B + 块 C 已完成且全部测试通过。本块是**最关键的一块**——把前 3 块产出的所有模块串联成一条完整的端到端流水线。

---

## 1. 需求描述

把块 C 的 4 个独立 Agent Layer 通过 LangGraph Orchestrator 串联，加上 Adapter 适配层、FastAPI 路由和 Human-in-the-Loop 机制，实现"用户提交 PRD → 系统自动生成技术方案文档"的完整流程。

### 核心功能列表

1. **Orchestrator 主编排**：主 StateGraph，按顺序调用 4 个 Layer
2. **Adapter 适配层**：每层外层包一个 Adapter，做 OrchestratorState ↔ LayerState 的转换
3. **迭代决策**：Evaluation 不通过时自动回退到 Planning 或 Generation
4. **Human-in-the-Loop**：分析结果和架构方案需要人工确认的节点
5. **异步任务**：`POST /api/v1/generate` 提交任务，`GET /api/v1/tasks/{id}` 查询进度
6. **评测接口**：`POST /api/v1/evaluate` 对已有方案进行评测
7. **人工审核接口**：`GET /api/v1/review/pending` + `POST /api/v1/review/{task_id}/{stage}`

---

## 2. 目标

| 目标 | 衡量标准 |
|------|---------|
| 全链路可跑通 | 输入样本 PRD → 输出完整技术方案文档（> 3000 字） |
| API 可用 | curl POST /api/v1/generate 返回 200 + task_id |
| 异步任务 | 任务提交后轮询 tasks/{id} 可看到进度变化 |
| 迭代决策 | Evaluation 低分时自动回退重做 |
| 块 A/B/C 不变 | 不修改已有 Layer 的任何接口签名 |

---

## 3. 使用技术栈

```yaml
# === 强制使用 ===
orchestrator: langgraph>=0.2.0           # 主 StateGraph
web: fastapi>=0.110                      # 继承块 A
test: pytest>=8.0 + pytest-asyncio
lint: ruff
type_check: mypy

# === 新增依赖 ===
new_deps:
  - httpx                                 # API 测试客户端

# === 异步任务 ===
task_queue: asyncio.create_task + in-memory dict  # 仍然不引入 celery/redis

# === 禁止引入 ===
forbidden:
  - langchain 任何包
  - celery                                # 块 E 才引入
  - redis                                 # 块 E 才引入
```

---

## 4. Coding 约束

### ⚠️ 块 D 铁律（违反则整个 Session 无效）

```
1. ❌ 禁止修改 contracts/interfaces.py 中已有的接口签名
2. ❌ 禁止修改各 Layer 的 run() 方法签名
3. ❌ 禁止在各 Layer 的 Node 内部直接引用 OrchestratorState
4. ✅ 各 Layer 外层包 Adapter，做状态映射
```

### Adapter 模式（必须遵守）

```python
# ✅ 正确：Adapter 做状态映射
class AnalysisAdapter:
    """Analysis Layer 的 Orchestrator Adapter。"""

    def __init__(self, analysis_graph: StateGraph):
        self.graph = analysis_graph

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """从 OrchestratorState 提取输入，调用 Analysis Layer，映射结果。"""
        # 1. 提取输入
        analysis_input = {
            "prd_raw": state["prd_raw"],
            "prd_file_type": state["prd_file_type"],
        }
        # 2. 调用块 C 的 Layer
        result = await self.graph.ainvoke(analysis_input)
        # 3. 映射回 OrchestratorState
        state["analysis_result"] = result["analysis_result"]
        state["extracted_requirements"] = result["extracted_requirements"]
        state["extracted_constraints"] = result["extracted_constraints"]
        return state

# ❌ 错误：在 Layer Node 内直接访问 OrchestratorState
class AnalysisNode:
    async def run(self, state: OrchestratorState) -> OrchestratorState:
        # 禁止 — 这会破坏 Layer 的独立性，使块 C 的测试失效
        ...
```

### 迭代决策逻辑

```python
class IterationDecider:
    """评估决策：根据评分决定后续路由。"""

    ROUTE_MAP = {
        "accept": "final_assembly",          # ✅ 通过
        "replan": "planning",                # 🔄 重新规划
        "regenerate": "generation",          # 🔄 重新生成
        "human_intervention": "human_review",# 🧑 人工介入
    }

    def run(self, state: OrchestratorState) -> str:
        report = state["evaluation_report"]
        if state["iteration_count"] >= state["max_iterations"]:
            return "accept"
        if report.overall_score >= 85:
            return "accept"
        elif report.overall_score >= 70:
            if report.dimension_scores.get("consistency", 100) < 70:
                return "regenerate"
            elif report.dimension_scores.get("feasibility", 100) < 70:
                return "replan"
            return "accept"
        else:
            state["iteration_count"] += 1
            return "replan"
```

---

## 5. 数据结构

### 5.1 OrchestratorState

```python
class TenantContext(BaseModel):
    """多租户上下文 — 贯穿所有 Layer 的租户隔离信息。"""
    organization_id: str
    workspace_id: str
    knowledge_scope: str                   # workspace / org / global
    settings: dict                         # 工作空间级别配置


class OrchestratorState(TypedDict):
    """主编排器状态 — 串联 4 个 Layer 的全局状态。"""

    # --- 输入 ---
    task_id: str
    prd_raw: str
    prd_file_type: str                     # md / pdf / docx
    workspace_id: str
    user_id: str
    user_role: str                         # 用户角色
    permissions: list[str]                 # 用户权限列表

    # --- 多租户上下文 ---
    tenant_context: TenantContext

    # --- 块 B 知识检索 ---
    knowledge_context: RetrievalContext

    # --- 块 C1 Analysis ---
    analysis_result: AnalysisResult
    extracted_requirements: list[Requirement]
    extracted_constraints: list[Constraint]

    # --- 块 C2 Planning ---
    planning_result: PlanningResult
    component_decomposition: list[Component]
    tech_stack_choices: list[TechChoice]

    # --- 块 C3 Generation ---
    generation_result: GenerationResult
    section_contents: dict[str, str]

    # --- 块 C4 Evaluation ---
    evaluation_report: EvaluationReport

    # --- 控制字段 ---
    iteration_count: int
    max_iterations: int
    status: Literal["running", "paused", "complete", "failed"]
    error_message: str = ""
    progress: float = 0.0                   # 0.0 ~ 1.0
```

### 5.2 任务状态模型

```python
class TaskInfo(BaseModel):
    """任务信息（API 返回）。"""
    task_id: str
    status: str
    progress: float
    result: GenerationResult | None = None
    evaluation: EvaluationReport | None = None
    error: str | None = None
    created_at: str
    updated_at: str
```

---

## 6. 要新增的文件

```
app/orchestrator/
├── __init__.py
├── main_graph.py                         # 主 StateGraph（串联 4 层）
├── state.py                              # OrchestratorState
├── routing.py                            # 条件路由（review 判断/迭代决策）
├── human_review.py                       # HumanReviewNode（interrupt 机制）
├── iteration.py                          # IterationDecider
└── adapters/
    ├── __init__.py
    ├── analysis_adapter.py               # Analysis Layer Adapter
    ├── planning_adapter.py               # Planning Layer Adapter
    ├── generation_adapter.py             # Generation Layer Adapter
    └── evaluation_adapter.py             # Evaluation Layer Adapter

app/api/routes/
├── generate.py                           # POST /api/v1/generate + GET /tasks/{id}
├── review.py                             # GET /review/pending + POST /review/{id}/{stage}
└── evaluate.py                           # POST /api/v1/evaluate

app/task_manager.py                       # 异步任务管理器（in-memory 队列）

tests/unit/
└── test_orchestrator.py                  # Orchestrator 单元测试

tests/integration/
└── test_pipeline.py                      # 完整端到端集成测试

tests/e2e/
└── test_full_flow.py                     # 真实全链路（含真实 LLM）
```

---

## 7. 模块联通（输入/输出接口）

### 本块对外输出

```
输出 → 块 E（企业功能）:
  - app/orchestrator/main_graph.py 编译后的主 StateGraph
  - app/task_manager.py 任务管理器（块 E 的会话历史会替换为 DB 存储）
  - app/api/main.py 应用入口（块 E 增加新路由）
```

### 本块对外输入

```
输入 ← 块 A:
  - app/main.py: FastAPI 应用实例
  - app/auth/deps.py: 权限依赖
  - app/core/llm.py: LLM 客户端

输入 ← 块 B:
  - RetrievalPipeline.retrieve()

输入 ← 块 C:
  - 4 个编译好的 StateGraph:
    analysis_graph, planning_graph, generation_graph, evaluation_graph
```

### 主 StateGraph 结构

```python
orchestrator = StateGraph(OrchestratorState)

# 添加节点（通过 Adapter 封装）
orchestrator.add_node("knowledge_retrieval", KnowledgeRetrievalNode(pipeline_b).run)
orchestrator.add_node("analysis", AnalysisAdapter(analysis_graph).run)
orchestrator.add_node("analysis_human_review", HumanReviewNode("analysis").run)
orchestrator.add_node("planning", PlanningAdapter(planning_graph).run)
orchestrator.add_node("planning_human_review", HumanReviewNode("planning").run)
orchestrator.add_node("generation", GenerationAdapter(generation_graph).run)
orchestrator.add_node("evaluation", EvaluationAdapter(evaluation_graph).run)
orchestrator.add_node("iteration_decider", IterationDecider().run)
orchestrator.add_node("final_assembly", FinalAssemblyNode().run)

# 连线
orchestrator.set_entry_point("knowledge_retrieval")
orchestrator.add_edge("knowledge_retrieval", "analysis")
orchestrator.add_conditional_edges("analysis", needs_review, {...})
orchestrator.add_edge("analysis_human_review", "planning")
orchestrator.add_conditional_edges("planning", needs_review, {...})
orchestrator.add_edge("planning_human_review", "generation")
orchestrator.add_edge("generation", "evaluation")
orchestrator.add_conditional_edges("evaluation", IterationDecider().run, {
    "accept": "final_assembly",
    "replan": "planning",
    "regenerate": "generation",
    "human_intervention": "analysis",
})
orchestrator.add_edge("final_assembly", END)
```

---

## 8. 部署架构

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
    ┌──────────┬──────────┬────┴────┬──────────┬──────────┐
    │          │          │         │          │          │
┌───▼──┐  ┌───▼──┐  ┌───▼───┐ ┌───▼──┐  ┌───▼──┐  ┌───▼──┐
│Neo4j │  │Post- │  │ Redis │ │MinIO │  │Pro-  │  │Grafana│
│      │  │gres  │  │       │ │      │  │me-   │  │       │
│图数据│  │向量+ │  │缓存+ │ │文档  │  │theus │  │监控  │
│库    │  │业务  │  │队列  │ │存储  │  │      │  │面板  │
└──────┘  └──────┘  └──────┘ └──────┘  └──────┘  └──────┘
```

---

## 9. 端到端数据流全景

```
                        ╔═══ 输入源 ═══╗
                        ║ .md/.pdf     ║
                        ║ .docx/.txt   ║
                        ║ .csv/.tsv    ║
                        ║ 图片/架构图  ║
                        ║ Web URL      ║
                        ╚══════════════╝
                              │
                      [数据脱敏引擎]
                              │
                      [多租户上下文注入]
                              │
  ┌───────────────────────────┼──────────────────────────────┐
  │  Layer 1: Knowledge Layer (块 B)                        │
  │  文档→分块→实体/关系提取→TextUnit→Neo4j+PGVector       │
  │  → Local/Global/Multimodal Search                       │
  └───────────────────────────┬──────────────────────────────┘
                              │
  ┌───────────────────────────┼──────────────────────────────┐
  │  Layer 2: Analysis Layer (块 C1)                        │
  │  PRD→章节解析→需求提取→约束分析→依赖分析→领域分类      │
  │  → AnalysisResult                                       │
  └───────────────────────────┬──────────────────────────────┘
                              │
  ┌───────────────────────────┼──────────────────────────────┐
  │  Layer 3: Planning Layer (块 C2)                        │
  │  AnalysisResult→知识增强→模式推荐→技术栈选型→组件分解   │
  │  →成本估算→时间线→技能缺口→风险量化→PlanningResult       │
  └───────────────────────────┬──────────────────────────────┘
                              │
  ┌───────────────────────────┼──────────────────────────────┐
  │  Layer 4: Generation Layer (块 C3)                      │
  │  PlanningResult→模板→大纲→逐节撰写→图表生成→代码框架    │
  │  →一致性检查→多格式导出→GenerationResult                │
  └───────────────────────────┬──────────────────────────────┘
                              │
  ┌───────────────────────────┼──────────────────────────────┐
  │  Evaluation System (块 C4)                              │
  │  覆盖度→一致性→可行性→质量→安全→评分校准→综合评分      │
  └───────────────────────────┬──────────────────────────────┘
                              │
            ┌─────────────────┼──────────────────┐
            │                 │                  │
       评分≥85            70≤评分<85         评分<70
            │                 │                  │
       交付方案         预警交付+回退       迭代重做
            │
        [多格式导出]
        [通知干系人]
        [审计日志]
```

---

## 10. 完整链路

```
API 请求链路:
  POST /api/v1/generate
    → Auth 中间件验证 JWT
    → PermissionChecker 检查权限
    → 脱敏引擎脱敏 PRD 中的敏感信息
    → TenantContext 注入
    → TaskManager.create_task() → 返回 task_id
    → 异步执行：

      1. Knowledge Retrieval（块 B）
         → RetrievalPipeline.retrieve(prd_raw) → RetrievalContext

      2. Analysis（块 C1）
         → AnalysisAdapter.run(state)
         → 内部: DocumentParser → RequirementExtractor → ... → AnalysisResult

      3. [可选] Human Review: 分析结果确认
         → 如果需确认，暂停等待人工反馈

      4. Planning（块 C2）
         → PlanningAdapter.run(state)
         → 内部: PatternRecommend → TechStackSelect → ... → PlanningResult

      5. [可选] Human Review: 架构方案确认

      6. Generation（块 C3）
         → GenerationAdapter.run(state)
         → 内部: Outline → SectionWriter → Diagram → ... → Markdown

      7. Evaluation（块 C4）
         → EvaluationAdapter.run(state)
         → 内部: Coverage → Consistency → Feasibility → ... → Score

      8. Iteration Decision
         → 评分 >= 85: 进入 FinalAssembly
         → 评分 >= 70: 根据具体维度回退
         → 评分 < 70: 回退到 Planning

      9. FinalAssembly
         → 组装完整 GenerationResult
         → 更新 task 状态为 complete

    → 用户轮询: GET /api/v1/tasks/{task_id}
    → 返回: {status: "complete", result: GenerationResult, evaluation: EvaluationReport}
```

---

## 9. 测试用例

### 9.1 Orchestrator 单元测试

```python
# tests/unit/test_orchestrator.py
async def test_orchestrator_runs_full_pipeline():
    """验证 Orchestrator 完整流程。"""
    state = await orchestrator.ainvoke({
        "task_id": "test-1",
        "prd_raw": sample_prd,
        "prd_file_type": "md",
    })
    assert state["status"] == "complete"
    assert state["generation_result"] is not None
    assert state["evaluation_report"] is not None

async def test_orchestrator_retries_on_low_score():
    """验证低分时自动回退。"""
    state = await orchestrator.ainvoke({"evaluation_report": low_score_report, ...})
    assert state["iteration_count"] >= 1

async def test_adapter_preserves_layer_independence():
    """验证 Adapter 不修改 Layer 内部逻辑。"""
    # 直接调用块 C 的 Layer，验证它仍然正常工作
    result = await analysis_graph.ainvoke({"prd_raw": sample_prd})
    assert len(result["extracted_requirements"]) > 0
```

### 9.2 集成测试

```python
# tests/integration/test_pipeline.py
async def test_full_pipeline_with_mock_llm():
    """验证全链路（Mock LLM 调用）。"""
    result = await run_pipeline(sample_prd)
    assert result.status == "complete"
    assert len(result.generation_result.content) > 1000

async def test_api_generate_endpoint():
    """验证 API 接口。"""
    client = TestClient(app)
    resp = await client.post("/api/v1/generate", json={
        "prd_content": sample_prd,
        "prd_type": "md",
    })
    assert resp.status_code == 200
    assert "task_id" in resp.json()

async def test_api_task_polling():
    """验证任务轮询。"""
    client = TestClient(app)
    resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("running", "complete")
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

# 3. 全部测试通过（含块 A/B/C 全部回归）
pytest tests/ -v --tb=short
# 100% passed, 0 skipped

# 4. 无 TODO 残留
grep -rn "TODO\|FIXME\|NotImplementedError" app/ --include="*.py" || echo "CLEAN"
```

### 联通性测试

```bash
# 1. 集成测试 — 全链路（Mock LLM）
pytest tests/integration/test_pipeline.py -v
# 期望: test_full_pipeline_with_mock_llm PASS
# 验证: result.status == "complete", document > 1000 字

# 2. 端到端 — 真实 LLM 调用
pytest tests/e2e/test_full_flow.py -v --slow
# 期望: test_full_flow PASS
# 输入: 样本 PRD .md
# 输出: 完整技术方案文档
# 验证: 文档长度 > 3000 字，包含 mermaid 图表

# 3. API smoke test
uvicorn app.api.main:app --port 8000 &

# 3a. 提交生成任务
curl -s -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prd_content": "# 测试\n## 功能\n1. 登录", "prd_type": "md"}'
# 期望: {"task_id": "...", "status": "running"}

# 3b. 查询任务状态
curl -s http://localhost:8000/api/v1/tasks/{task_id}
# 期望: {"status": "complete", "result": {...}}

# 4. 回归块 A/B/C
pytest tests/integration/test_auth_flow.py -v
pytest tests/integration/test_kg_build.py -v
pytest tests/integration/test_analysis_pipeline.py -v
```

### 完成后状态

```
✅ POST PRD → 系统自动生成完整技术方案文档
✅ API 异步接口可用（提交 + 轮询）
✅ Evaluation 低分时自动迭代
✅ Human-in-the-Loop 机制就绪
✅ 所有块 A/B/C 回归测试全绿
✅ 可进入块 E 开发
```
