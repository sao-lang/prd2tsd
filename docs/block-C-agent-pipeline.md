# 块 C：核心 Agent 流水线

> 关联总文档：`prd2tsd.md` §四 Analysis Layer、§五 Planning Layer、§六 Generation Layer、§七 Evaluation System
>
> **前置条件**：块 A + 块 B 已完成且全部测试通过。本块使用块 A 的 Contract 接口定义 + LLM Gateway + Auth 中间件 + 数据脱敏引擎，使用块 B 的 RetrievalPipeline 进行知识检索。

---

## 1. 需求描述

构建 4 个独立的 Agent Layer，每个 Layer 是一个 LangGraph StateGraph，可在输入 Mock 数据时独立运行和测试。

### 核心功能列表

**C1 — Analysis Layer（分析层）**
- 文档解析为结构化章节
- 需求提取（功能 + 非功能）
- 约束条件提取
- 需求依赖关系分析
- 领域分类
- ⭐ 多语言 PRD 支持（自动检测中/英/混合，英文自动翻译）
- ⭐ 需求质量评分（完整性/清晰度/可测试性/一致性/必要性/可行性 6 维）
- ⭐ 工作量估算（COCOMO II + LLM 调整）
- ⭐ 干系人分析（提取干系人及其关注点）
- 结果组装为 AnalysisResult

**C2 — Planning Layer（规划层）**
- 从块 B 检索相关知识上下文
- 架构模式推荐（2-3 候选 + 对比）
- 技术栈选型（按维度分批决策）
- 组件分解（需求 → 组件映射）
- 数据架构设计
- API 规划草稿
- 部署方案草稿
- ⭐ 成本估算（低成本/标准/高可用 3 种方案）
- ⭐ 时间线规划（甘特图 + 里程碑）
- ⭐ 技能缺口分析（当前团队技能 vs 方案需求）
- ⭐ 风险量化（概率×影响矩阵）
- 自检 → 回退或通过
- 结果组装为 PlanningResult

**C3 — Generation Layer（生成层）**
- 大纲生成（14 个标准章节）
- ⭐ 模板系统（行业/企业/章节三级模板，Jinja2 渲染）
- 逐节撰写（支持并行写多节）
- Mermaid 架构图自动生成
- 一致性检查 + 修复
- ⭐ 代码框架生成（真实可编译代码，非描述文本）
- ⭐ 多格式导出（Markdown / PDF / DOCX / HTML）
- Markdown 格式组装

**C4 — Evaluation System（评测层）**
- PRD 覆盖率检查
- 内部一致性检查
- 技术可行性评估
- 架构质量评分
- 安全合规检查
- 10 维加权综合评分
- ⭐ 评分校准（历史比对校准 + 平行评测校准 + 反馈闭环）

---

## 2. 目标

| 目标 | 衡量标准 |
|------|---------|
| 4 层独立可跑 | 每层输入 Mock 数据时，输出正确结构的 Result |
| 层层串联 | AnalysisResult → PlanningResult → GenerationResult → EvaluationReport |
| 块 B 集成 | Planning Layer 的 KnowledgeAugmentNode 调用块 B 的 Pipeline |
| 输出完整方案 | 最终 EvaluationReport 的 overall_score 有值 |

---

## 3. 使用技术栈

```yaml
# === 强制使用 ===
agent_framework: langgraph>=0.2.0        # StateGraph（禁止 AgentExecutor）
llm_client: openai>=1.0                  # 继承块 A，兼容 DeepSeek API

# === 模型分配（严格遵守）===
model_routing:
  analysis.requirement: deepseek-v3      # 需求提取要精确
  analysis.constraint: deepseek-v3
  planning.pattern: deepseek-v3          # 架构创意
  planning.tech_stack: deepseek-v3
  planning.self_check: gpt-4o-mini       # 自检用低成本
  generation.section_writer: deepseek-v3 # 写作量大用便宜的
  generation.consistency: gpt-4o-mini
  evaluation.scoring: gpt-4o-mini        # Judge 用便宜模型
  evaluation.security: deepseek-v3       # 安全合规要严谨

test: pytest>=8.0 + pytest-asyncio
lint: ruff
type_check: mypy

# === 禁止引入 ===
forbidden:
  - langchain, langchain-community, langchain-openai  # 全家桶禁止
  - langgraph 的旧版本（必须 >= 0.2.0）
  - redis, celery (异步任务用 asyncio.create_task + in-memory 队列)
```

---

## 4. Coding 约束

### LangGraph 使用规范

```python
# ✅ 正确：使用 StateGraph
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

class AnalysisState(TypedDict):
    prd_raw: str
    requirements: list[Requirement]
    # ...

graph = StateGraph(AnalysisState)
graph.add_node("parse", DocumentParserNode().run)
graph.add_node("extract", RequirementExtractorNode().run)
graph.set_entry_point("parse")
graph.add_edge("parse", "extract")
graph.add_edge("extract", END)

# ❌ 错误
# from langchain.agents import AgentExecutor  # 禁止
# from langchain.chains import LLMChain      # 禁止
```

### 4 层解耦约束

```
┌────────────────────────────────────────────────────────────┐
│  4 个 Layer 之间 100% 通过 contracts/interfaces.py 解耦     │
│                                                             │
│  C1 (Analysis) 输出 → AnalysisResult                        │
│  C2 (Planning)  输入 AnalysisResult，输出 → PlanningResult  │
│  C3 (Generation) 输入 PlanningResult，输出 → GenerationResult│
│  C4 (Evaluation) 输入全部三个 Result，输出 → EvaluationReport│
│                                                             │
│  ❌ 禁止：C2 的 Node 直接 import C1 的 Node                  │
│  ❌ 禁止：任何 Layer 直接引用 OrchestratorState               │
│  ✅ 允许：通过 contracts/models.py 共享数据模型               │
└────────────────────────────────────────────────────────────┘
```

### 其他约束

```
- 每个 Node 的 run() 方法签名必须统一: run(state: LayerState) -> LayerState
- 每个函数 ≤ 50 行，每个文件 ≤ 300 行
- 每个 public 函数必须有 type hint + Google 风格 docstring
- 禁止 TODO / FIXME / pass / raise NotImplementedError
- 对于不属于块 C 的功能（如增强节点），用 VIBE_DEFER(块 E) 标记
```

---

## 5. 数据结构

### 5.1 C1 — AnalysisState

```python
class AnalysisState(TypedDict):
    """分析层状态"""
    prd_raw: str
    prd_sections: list[DocumentSection]
    extracted_requirements: list[Requirement]
    extracted_entities: list[KGEntity]
    extracted_constraints: list[Constraint]
    dependency_graph: DependencyGraph
    domain_tags: list[str]
    analysis_result: AnalysisResult
    confidence: float

class Requirement(BaseModel):
    id: str                               # FR-001 / NFR-001
    type: Literal["functional", "non_functional"]
    category: str                         # 用户管理 / 订单处理 / 性能 / 安全
    priority: Literal["P0", "P1", "P2", "P3"]
    description: str
    actor: str
    acceptance_criteria: list[str] = []
    source_section: str

class Constraint(BaseModel):
    type: Literal["technical", "performance", "time", "budget", "compliance", "team"]
    description: str
    severity: Literal["must", "should", "could"]
    source_section: str

class AnalysisResult(BaseModel):
    project_name: str
    summary: str
    domain_tags: list[str]
    requirements: list[Requirement]
    constraints: list[Constraint]
    dependency_graph: DependencyGraph
    confidence: float
```

### 5.2 C2 — PlanningState

```python
class PlanningState(TypedDict):
    analysis_result: AnalysisResult
    knowledge_context: RetrievalContext
    architecture_patterns: list[PatternEval]
    selected_pattern: str
    tech_stack_choices: list[TechChoice]
    component_decomposition: list[Component]
    planning_result: PlanningResult

class PatternEval(BaseModel):
    pattern_name: str
    match_score: float
    strengths: list[str]
    weaknesses: list[str]
    complexity: Literal["low", "medium", "high"]

class TechChoice(BaseModel):
    dimension: str                        # backend_framework / database_primary
    recommendation: str
    reason: str
    alternatives: list[dict]
    risks: list[str]

class Component(BaseModel):
    name: str
    type: Literal["service", "module", "library"]
    responsibility: str
    key_functions: list[str]
    dependencies: list[str]

class PlanningResult(BaseModel):
    architecture_pattern: str
    tech_stack: list[TechChoice]
    components: list[Component]
    component_diagram: str                # Mermaid 代码
```

### 5.3 C3 — GenerationState

```python
class GenerationState(TypedDict):
    planning_result: PlanningResult
    analysis_result: AnalysisResult
    outline: list[SectionOutline]
    section_contents: dict[str, str]      # {section_id: content}
    generation_result: GenerationResult

class SectionOutline(BaseModel):
    section_id: str
    title: str
    level: int
    description: str
    estimated_tokens: int

class GenerationResult(BaseModel):
    content: str                          # 完整 Markdown 文档
    sections: dict[str, str]              # {section_id: markdown_content}
    mermaid_diagrams: dict[str, str]      # {diagram_type: mermaid_code}
```

### 5.4 C4 — EvaluationState

```python
class EvaluationState(TypedDict):
    analysis_result: AnalysisResult
    planning_result: PlanningResult
    generation_result: GenerationResult
    evaluation_report: EvaluationReport

class EvaluationReport(BaseModel):
    overall_score: float
    dimension_scores: dict                # {dimension: score}
    conclusion: Literal["通过", "预警通过", "不通过"]
    p0_coverage: float
    critical_issues: list[dict]
    recommendations: list[str]
```

---

## 6. 要新增的文件

```
app/
├── analysis_layer/
│   ├── __init__.py
│   ├── agent_graph.py                   # LangGraph StateGraph
│   ├── models.py                        # AnalysisState, AnalysisResult
│   ├── tools.py                         # 工具函数
│   └── nodes/
│       ├── __init__.py
│       ├── parse_node.py                # DocumentParserNode
│       ├── requirement_node.py          # RequirementExtractorNode
│       ├── constraint_node.py           # ConstraintAnalyzerNode
│       ├── dependency_node.py           # DependencyAnalyzerNode
│       ├── domain_classifier.py         # DomainClassifierNode
│       ├── lang_detector.py             # ⭐ LanguageDetectorNode（多语言支持）
│       ├── quality_scorer.py            # ⭐ RequirementQualityNode（6维评分）
│       ├── effort_estimator.py          # ⭐ EffortEstimatorNode（COCOMO II）
│       ├── stakeholder_analyzer.py      # ⭐ StakeholderAnalyzerNode
│       ├── clarity_checker.py           # ClarityCheckerNode
│       └── result_assembler.py          # AnalysisResultAssemblerNode

├── planning_layer/
│   ├── __init__.py
│   ├── agent_graph.py                   # LangGraph StateGraph
│   ├── models.py                        # PlanningState, PlanningResult
│   ├── tools.py
│   └── nodes/
│       ├── __init__.py
│       ├── knowledge_augment.py         # KnowledgeAugmentNode（调块 B Pipeline）
│       ├── pattern_recommend.py         # PatternRecommendNode
│       ├── pattern_confirm.py           # PatternConfirmNode
│       ├── tech_stack_select.py         # TechStackSelectNode
│       ├── component_decompose.py       # ComponentDecomposeNode
│       ├── cost_estimator.py            # ⭐ CostEstimatorNode（3种方案）
│       ├── timeline_planner.py          # ⭐ TimelinePlannerNode（甘特图）
│       ├── skill_gap_analyzer.py        # ⭐ SkillGapAnalyzerNode
│       ├── risk_quantifier.py           # ⭐ RiskQuantifierNode（概率×影响）
│       ├── data_arch_design.py          # DataArchDesignNode（轻量）
│       ├── api_planning.py              # APIPlanningNode（轻量）
│       ├── deployment_planning.py       # DeploymentPlanningNode（轻量）
│       ├── plan_self_check.py           # PlanSelfCheckNode
│       └── plan_assembler.py            # PlanAssemblerNode

├── generation_layer/
│   ├── __init__.py
│   ├── agent_graph.py                   # LangGraph StateGraph
│   ├── models.py                        # GenerationState, GenerationResult
│   ├── tools.py
│   │
│   ├── templates/                       # ⭐ 模板系统
│   │   ├── __init__.py
│   │   ├── engine.py                    # 模板引擎（Jinja2）
│   │   ├── industry/                    # 行业模板
│   │   │   ├── ecommerce.yaml
│   │   │   └── default.yaml
│   │   └── section/                     # 章节模板
│   │       ├── background.md
│   │       └── architecture.md
│   │
│   └── nodes/
│       ├── __init__.py
│       ├── outline_node.py              # OutlineGeneratorNode
│       ├── section_writer.py            # SectionWriterNode
│       ├── diagram_generator_node.py    # Mermaid 图表生成
│       ├── code_scaffold_node.py        # ⭐ CodeScaffoldGeneratorNode（真实代码）
│       ├── consistency_checker.py       # ConsistencyCheckerNode
│       ├── revision_node.py             # RevisionNode
│       ├── format_assembler.py          # FormatAssemblerNode
│       └── format_exporter.py           # ⭐ 多格式导出（PDF/DOCX/HTML）

└── evaluation/
    ├── __init__.py
    ├── agent_graph.py                   # LangGraph StateGraph
    ├── models.py                        # EvaluationState, EvaluationReport
    ├── scoring.py                       # ScoringNode（10维加权）
    ├── score_calibrator.py              # ⭐ 评分校准（历史比对+平行评测）
    └── nodes/
        ├── __init__.py
        ├── coverage.py                  # PRDCoverageCheckNode
        ├── consistency.py               # ConsistencyEvalNode
        ├── feasibility.py               # FeasibilityEvalNode
        ├── architecture_quality.py      # ArchitectureQualityNode
        ├── security_compliance.py       # SecurityComplianceNode
        ├── cost_eval.py                 # ⭐ 成本合理性评估
        ├── implementability_eval.py     # ⭐ 可实施性评估
        ├── tech_advancement_eval.py     # ⭐ 技术先进性评估
        ├── legal_compliance_eval.py     # ⭐ 法律合规评估
        └── scoring.py                   # ScoringNode

tests/unit/
├── test_analysis_nodes.py               # 每个 Node 独立测试
├── test_planning_nodes.py
├── test_generation_nodes.py
├── test_evaluation_nodes.py
├── test_score_calibrator.py             # ⭐ 评分校准测试
├── test_template_engine.py              # ⭐ 模板引擎测试
└── test_format_exporter.py              # ⭐ 多格式导出测试

tests/integration/
├── test_analysis_pipeline.py            # C1 集成测试
├── test_planning_pipeline.py            # C2 集成测试
├── test_generation_pipeline.py          # C3 集成测试
└── test_evaluation_pipeline.py          # C4 集成测试
```

---

## 7. 模块联通（输入/输出接口）

### 本块对外输出

```
输出 → 块 D（全链路串联）:
  - 4 个 Layer 的 agent_graph（已编译的 StateGraph）
  - 4 个 Layer 的 run() 方法
    分析层:   analysis_graph.ainvoke(state) → AnalysisState
    规划层:   planning_graph.ainvoke(state) → PlanningState
    生成层:   generation_graph.ainvoke(state) → GenerationState
    评测层:   evaluation_graph.ainvoke(state) → EvaluationState
```

### 本块对外输入

```
输入 ← 块 A:
  - app/core/llm.py: get_llm() → LLM 客户端
  - app/core/config.py: settings
  - contracts/interfaces.py: 所有接口定义

输入 ← 块 B:
  - RetrievalPipeline.retrieve(query, mode, top_k) → RetrievalContext
```

### 块内部联通

```
C1 (Analysis) ──→ AnalysisResult ──→ C2 (Planning)
                                        │
                          PlanningResult │
                                        ▼
                              C3 (Generation)
                                        │
                          GenerationResult
                                        ▼
                              C4 (Evaluation)
                                        │
                          EvaluationReport
```

每个 Layer 的 Node 之间通过 State 传递数据，不跨 Layer 调用。

---

## 8. 完整链路

```
C1 — Analysis Layer 链路（增强版）:
  输入: PRD 原始文本
    → DocumentParserNode: 按 Markdown 标题拆章节
    → LanguageDetectorNode: 检测语言（中/英/混合），英文自动翻译
    → RequirementExtractorNode: LLM 提取需求列表
    → ConstraintAnalyzerNode: LLM 提取约束
    → DependencyAnalyzerNode: LLM 分析需求依赖
    → DomainClassifierNode: 领域分类
    → RequirementQualityNode: 6 维质量评分
    → EffortEstimatorNode: COCOMO II 工作量估算
    → StakeholderAnalyzerNode: 干系人分析
    → ClarityCheckerNode: 检查是否清晰
    → ResultAssemblerNode: 组装 AnalysisResult
  输出: AnalysisResult

C2 — Planning Layer 链路（增强版）:
  输入: AnalysisResult
    → KnowledgeAugmentNode: 调块 B Pipeline 检索相关知识
    → PatternRecommendNode: LLM 推荐 2-3 种架构模式
    → PatternConfirmNode: 选择最优模式
    → TechStackSelectNode: 按维度分批选技术栈
    → ComponentDecomposeNode: 需求→组件映射
    → CostEstimatorNode: 3 种成本方案估算
    → TimelinePlannerNode: 甘特图+里程碑生成
    → SkillGapAnalyzerNode: 技能缺口分析
    → RiskQuantifierNode: 风险概率×影响量化
    → DataArchDesignNode: 数据架构
    → PlanSelfCheckNode: 自检（不通过则回退）
    → PlanAssemblerNode: 组装 PlanningResult
  输出: PlanningResult

C3 — Generation Layer 链路（增强版）:
  输入: PlanningResult + AnalysisResult
    → TemplateEngine.select_template(): 匹配行业/企业模板
    → OutlineGeneratorNode: 生成 14 节大纲（模板驱动）
    → SectionWriterNode: 逐节撰写（模板渲染 + 每次 1-2 节）
    → DiagramGeneratorNode: 生成 Mermaid 架构图
    → CodeScaffoldGeneratorNode: 生成可编译代码框架
    → ConsistencyCheckerNode: 一致性检查
    → RevisionNode: 修复问题
    → FormatAssemblerNode: 组装为完整 Markdown
    → FormatExporterNode: 导出为 PDF/DOCX/HTML
  输出: GenerationResult

C4 — Evaluation Layer 链路（增强版）:
  输入: AnalysisResult + PlanningResult + GenerationResult
    → PRDCoverageCheckNode: 逐条核对 PRD 需求是否覆盖
    → ConsistencyEvalNode: 方案内部一致性
    → FeasibilityEvalNode: 技术可行性
    → ArchitectureQualityNode: 架构质量评分
    → SecurityComplianceNode: 安全合规检查
    → CostEvalNode: 成本合理性评估
    → ImplementabilityEvalNode: 可实施性评估
    → TechAdvancementEvalNode: 技术先进性评估
    → LegalComplianceEvalNode: 法律合规评估
    → ScoreCalibratorNode: 历史比对 + 平行评测校准
    → ScoringNode: 10 维加权总分
  输出: EvaluationReport
```

---

## 9. 测试用例

### 9.1 C1 — Analysis 测试

```python
# tests/integration/test_analysis_pipeline.py
async def test_analysis_extracts_requirements():
    """验证 Analysis Layer 能从 PRD 中提取需求。"""
    prd = "# 项目名称：电商平台\n## 功能需求\n1. 用户登录\n2. 商品搜索"
    result = await analysis_graph.ainvoke({"prd_raw": prd})
    assert len(result["extracted_requirements"]) >= 2
    assert result["analysis_result"].project_name == "电商平台"

async def test_analysis_detects_constraints():
    """验证约束提取。"""
    prd = "## 约束条件\n必须使用Java 17"
    result = await analysis_graph.ainvoke({"prd_raw": prd})
    assert any("Java" in c.description for c in result["extracted_constraints"])
```

### 9.2 C2 — Planning 测试

```python
# tests/integration/test_planning_pipeline.py
async def test_planning_recommends_patterns():
    """验证 Planning Layer 推荐架构模式。"""
    result = await planning_graph.ainvoke({
        "analysis_result": mock_analysis_result,
        "knowledge_context": mock_knowledge,
    })
    assert len(result["architecture_patterns"]) >= 2
    assert result["planning_result"].architecture_pattern is not None

async def test_planning_decomposes_components():
    """验证组件分解。"""
    result = await planning_graph.ainvoke({...})
    assert len(result["component_decomposition"]) >= 3
```

### 9.3 C3 — Generation 测试

```python
# tests/integration/test_generation_pipeline.py
async def test_generation_produces_markdown():
    """验证生成层输出 Markdown 文档。"""
    result = await generation_graph.ainvoke({...})
    assert len(result["generation_result"].content) > 500
    assert "```mermaid" in result["generation_result"].content

async def test_generation_outline_has_required_sections():
    """验证大纲包含必需章节。"""
    required = ["项目概述", "总体架构", "模块详细设计"]
    for sec in required:
        assert any(sec in o.title for o in result["outline"])
```

### 9.4 C4 — Evaluation 测试

```python
# tests/integration/test_evaluation_pipeline.py
async def test_evaluation_scores_all_dimensions():
    """验证 10 维评分均有值。"""
    result = await evaluation_graph.ainvoke({...})
    report = result["evaluation_report"]
    assert len(report.dimension_scores) == 10
    assert 0 <= report.overall_score <= 100

async def test_evaluation_detects_missing_coverage():
    """验证覆盖率检查能发现未覆盖的需求。"""
    report = await evaluate(mock_analysis, mock_planning, mock_generation)
    assert report.p0_coverage <= 1.0
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

# 3. 全部测试通过（含块 A + 块 B 回归）
pytest tests/ -v --tb=short
# 100% passed, 0 skipped

# 4. 无 TODO 残留
grep -rn "TODO\|FIXME\|NotImplementedError" app/ --include="*.py" || echo "CLEAN"
```

### 联通性测试

```bash
# C1: Analysis Layer 独立测试
pytest tests/integration/test_analysis_pipeline.py -v
# 输入: 样本 PRD
# 输出: AnalysisResult（requirements >= 3）

# C2: Planning Layer 独立测试
pytest tests/integration/test_planning_pipeline.py -v
# 输入: Mock AnalysisResult
# 输出: PlanningResult（components >= 3）

# C3: Generation Layer 独立测试
pytest tests/integration/test_generation_pipeline.py -v
# 输入: Mock PlanningResult
# 输出: Markdown 文档（含 ```mermaid ```）

# C4: Evaluation Layer 独立测试
pytest tests/integration/test_evaluation_pipeline.py -v
# 输入: Mock 三层 Result
# 输出: EvaluationReport（10 维评分）

# 回归块 A + 块 B
pytest tests/integration/test_auth_flow.py -v
pytest tests/integration/test_kg_build.py -v
```

### 完成后状态

```
✅ 4 个 Layer 各自独立可运行
✅ Analysis Layer: 多语言支持 + 需求质量评分 + 工作量估算 + 干系人分析
✅ Planning Layer: 成本估算（3方案） + 时间线（甘特图） + 技能缺口 + 风险量化
✅ Generation Layer: 模板系统 + 真实代码框架 + PDF/DOCX/HTML 导出
✅ Evaluation: 扩展至 10 维评分 + 评分校准（历史比对+平行评测）
✅ Analysis → Planning → Generation → Evaluation 数据流正确
✅ Planning Layer 可调用块 B 的检索能力
✅ 每层都有完整测试覆盖
✅ 块 A + 块 B 回溯测试全绿
✅ 可进入块 D 开发
```
