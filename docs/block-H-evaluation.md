# 块 H：RAG + Agent 评测体系（引入 deepeval）

> **AI Summary**: 建立可复现的 RAG 检索/回答质量评测 + Agent 能力评测，形成"评测 → 定位短板 → 优化 → 再评测"闭环。RAG 用 deepeval 四指标，Agent 用"离线基准 + rubric 化 LLM-judge + 过程指标"三层组合。

## 1. 背景与目标

### 1.1 现状问题

| 现状 | 缺口 |
|------|------|
| `app/evaluation/` 只对**生成方案**做 10 维评分 | 不是 RAG/Agent 评测 |
| 无 `deepeval`、无黄金数据集、无检索/回答质量指标 | 检索好坏无法量化 |
| 无任务完成率/迭代轮数/人工介入率等过程指标 | agent 行为无法量化 |
| `observability/replay/` 只记录决策轨迹，不打分 | 有"数据"无"结论" |
| `ReflectionJudge` 反思有无价值未验证 | 无 A/B 证据 |

### 1.2 目标

- 建立可运行、可复现的 RAG 评测（检索 + 回答质量）
- 建立 Agent 评测（任务完成率 + 过程指标 + 结果质量）
- 评测结果能反哺优化（对比实验 → 定位短板 → 调整 → 复测）
- 用 A/B 数据回答"反思（ReflectionJudge）是否真的有用"

### 1.3 范围（只评测，不动追踪/社区检测）

本块只做评测相关改动，不涉及全链路追踪、Prometheus、社区检测。

---

## 2. 评测对象与两条路径

| 路径 | 入口 | 评测内容 |
|------|------|---------|
| **知识问答路径** | `RetrievalPipeline.retrieve()` → LLM 回答 | 检索质量 + 回答质量（RAG） |
| **复杂生成路径** | 主编排（Analysis→Planning→Generation→Evaluation） | 端到端 agent 能力 |

---

## 3. 评测指标分层

| 层 | 指标 | 计算方式 | 数据来源 | 回答的问题 |
|----|------|---------|---------|-----------|
| L1 检索质量 | `context_precision`、`context_recall` | deepeval | 黄金上下文 | 检索对不对、全不全 |
| L2 回答质量 | `faithfulness`、`answer_relevancy` | deepeval | 黄金答案 | 答得忠不忠实、切不切题 |
| L3 Agent 过程 | 任务完成率、迭代轮数、是否需人工 review、检索/反思次数、token/成本/延迟 | 自定义（复用 `replay/` 轨迹） | 运行轨迹 | 卡在哪一步、贵不贵 |
| L4 Agent 结果 | rubric 化 LLM-judge（P0 达成 / 可实施 / 完整性 / 一致性） | LLM-as-judge + 评分标准 | 生成结果 | 方案质量分 |

---

## 4. 数据集设计（离线基准）

### 4.1 目录与格式

```
tests/eval/
├── datasets/
│   ├── rag_qa.json          # RAG 黄金数据（知识问答）
│   └── agent_tasks.json     # Agent 任务数据（复杂生成）
└── reports/                 # 评测输出报告（gitignore）
```

### 4.2 `rag_qa.json` schema

```json
{
  "version": "1.0",
  "description": "RAG 知识问答黄金评测集",
  "samples": [
    {
      "id": "rag_001",
      "query": "用户服务用了什么技术栈？",
      "reference_answer": "用户服务使用 Spring Boot，依赖 PostgreSQL 数据库……",
      "reference_contexts": [
        "用户服务基于 Spring Boot 构建",
        "数据存储使用 PostgreSQL"
      ],
      "source_file": "tests/fixtures/sample_prd.md",
      "expected_mode": "hybrid"
    }
  ]
}
```

- `reference_contexts`：期望检索命中的关键上下文（用于 `context_precision/recall`）
- `reference_answer`：黄金答案（用于 `faithfulness/answer_relevancy`）
- 起步 **10-20 条**，基于现有 `tests/fixtures/sample_prd.md` 等 fixture 手工标注

### 4.3 `agent_tasks.json` schema

```json
{
  "version": "1.0",
  "samples": [
    {
      "id": "agent_001",
      "task": "根据给定 PRD 生成技术方案",
      "prd_input": "（PRD 文本或 fixture 路径）",
      "expected_key_points": ["架构选型", "数据库设计", "API 设计", "部署方案"],
      "rubric": {
        "p0_coverage": "是否覆盖全部 P0 需求（是/否）",
        "implementability": "方案是否可落地（0-10）",
        "consistency": "各章节是否自洽（0-10）"
      },
      "expected_max_iterations": 2
    }
  ]
}
```

---

## 5. 模块设计

### 5.1 `app/evaluation/rag/`（RAG 评测器）

```
app/evaluation/rag/
├── __init__.py        # 导出 RagEvaluator / RagEvalReport
├── models.py          # RagSample / RagEvalReport / RagQueryScore
├── dataset_loader.py  # 加载 rag_qa.json → list[RagSample]
└── evaluator.py       # RagEvaluator：跑检索+回答 → deepeval 指标 → 报告
```

**`RagEvaluator` 职责：**
1. 对每个 `RagSample`：调用 `RetrievalPipeline.retrieve(query)` 得到 `RetrievalContext`；用 LLM（`gateway.complete`，`task_type="knowledge_qa"`）生成回答
   - 注：`resolve_model` 对未配置路由的 `task_type` 降级到 deepseek-chat；若需用 judge 模型（gpt-4o-mini）评测回答质量，显式传 `model=`
2. 组装 deepeval 输入：`LLMTestCase(input=query, actual_output=LLM回答, retrieval_context=contexts, expected_output=reference_answer)`
3. 用 deepeval `evaluate()` 计算 L1+L2 四指标
4. 附带过程信息：`mode`、`results 数`、`反思轮数`、`total_tokens`
5. 输出 `RagEvalReport`（汇总分 + 按 query 明细 + 配置）

### 5.2 `app/evaluation/agent/`（Agent 评测器）

```
app/evaluation/agent/
├── __init__.py        # 导出 AgentEvaluator / AgentEvalReport
├── models.py          # AgentTask / AgentEvalReport / ProcessMetrics
└── evaluator.py       # AgentEvaluator：跑任务 → 过程指标 + judge 评分 → 报告
```

**`AgentEvaluator` 职责：**
1. 对每个 `AgentTask`：调用主编排图（`orchestrator.astream`，复用 `task_manager` 的启动方式）
2. **L3 过程指标**：任务完成率（是否到 `complete`）、迭代轮数、是否需人工 review、各阶段耗时
3. **L4 结果质量**：按 `rubric` 用 judge 模型（`gateway.complete`，`task_type="evaluation_scoring"`）打分，LLM 返回结构化 JSON
4. 输出 `AgentEvalReport`（汇总 + 按任务明细）

---

## 6. 脚本设计（CLI 入口，不加 API）

### 6.1 `scripts/run_rag_eval.py`

```bash
# 基础评测
python scripts/run_rag_eval.py --dataset tests/eval/datasets/rag_qa.json

# 对比实验（多组配置）
python scripts/run_rag_eval.py --variant '{"top_k": 5, "reflection": true}'
python scripts/run_rag_eval.py --variant '{"top_k": 10, "reflection": false}'

# 反思 A/B（默认输出反思开/关对比）
python scripts/run_rag_eval.py --ab-reflection
```

- `--variant`：覆盖检索配置（`top_k` / `reflection` / `mode`），对比输出
- 输出：`tests/eval/reports/rag_eval_<ts>.json`（含对比表）
- `--ab-reflection`：同数据集跑反思开/关两组，输出指标差

### 6.2 `scripts/run_agent_eval.py`

```bash
python scripts/run_agent_eval.py --dataset tests/eval/datasets/agent_tasks.json
```

- 输出：`tests/eval/reports/agent_eval_<ts>.json`
- 含：完成率 / 平均迭代轮数 / 人工介入率 / judge 均分

---

## 7. 反思（ReflectionJudge）A/B 验证

> 只验证、不改逻辑。

- 在 `run_rag_eval.py` 中，对同一数据集跑 `reflection=true` / `reflection=false` 两组
- 对比指标：`context_recall` / `context_precision` / `faithfulness` + 耗时/成本
- 结论写入 `overview.md`：反思是否真的提升指标（若提升 < 阈值或负提升，建议默认关闭反思，仅按需开启）

---

## 8. 优化闭环

```
跑评测 → 看短板 → 改 → 重跑 → 指标提升才算有效
```

| 短板信号 | 可能优化点 |
|---------|-----------|
| `context_recall` 低 | 调 `top_k` / 反思 / 检索模式 |
| `context_precision` 低 | 调重排（reranker）/ 压缩 |
| `faithfulness` 低 | 改回答 prompt（更严格"基于上下文"） |
| 迭代轮数高 | 优化 planning / 评测反馈注入 |
| 人工介入率高 | 优化生成质量，减少 review 需求 |

每次评测结论追加到 `overview.md`（时间倒序，含数据集/配置/指标/结论）。

---

## 9. 依赖

| 依赖 | 位置 | 说明 |
|------|------|------|
| `deepeval>=4,<5` | `requirements.txt` + `pyproject.toml` | 评测框架（2026-08 已与 langchain 1.x / langgraph 1.x / Python 3.14 实测兼容） |

- judge 模型复用现有配置：`MODEL_CONFIG__JUDGE__OPENAI__DEFAULT_MODEL=gpt-4o-mini`
- embedding 复用现有配置：`MODEL_CONFIG__EMBEDDING__OPENAI__DEFAULT_MODEL=text-embedding-3-small`
- deepeval 具体 API（`evaluate` / `Metrics` / `LLMTestCase`）以安装版本官方文档为准
- **deepeval judge 模型不经过项目 gateway**：通过 `OpenAIModel` 注入 judge 配置（`api_key` / `base_url` / `default_model`），复用项目 OpenAI 兼容端点；原生 L1/L2 四指标不需要 embedding

---

## 10. 测试

| 测试 | 内容 | Mock/真实 |
|------|------|----------|
| `tests/unit/test_rag_eval.py` | `RagEvaluator` 指标计算与报告结构（mock LLM/检索） | Mock |
| `tests/unit/test_agent_eval.py` | `AgentEvaluator` 过程指标与 judge 解析（mock 图/LLM） | Mock |
| 冒烟 | 用 `rag_qa.json` 真实跑通 deepeval `evaluate()` | 真实 LLM |
| E2E（可选） | 完整评测脚本跑通 | 真实 |

---

## 11. 逐文件 Checklist

### A. 依赖

- [x] **`requirements.txt`**：新增 `deepeval>=4,<5`
- [x] **`pyproject.toml`**：`dependencies` 同步新增 `deepeval>=4,<5`

### B. 新增 RAG 评测模块

- [ ] **`app/evaluation/rag/__init__.py`**（新增）：导出 `RagEvaluator`、`RagEvalReport`、`RagSample`
- [ ] **`app/evaluation/rag/models.py`**（新增）：
  - `RagSample`：`id/query/reference_answer/reference_contexts/source_file/expected_mode`
  - `RagQueryScore`：`sample_id/context_precision/context_recall/faithfulness/answer_relevancy/retrieved_count/reflection_rounds/total_tokens`
  - `RagEvalReport`：`dataset_version/config/summary(RagEvalSummary)/queries(list[RagQueryScore])/timestamp`
- [ ] **`app/evaluation/rag/dataset_loader.py`**（新增）：`load_rag_dataset(path) -> list[RagSample]`
- [ ] **`app/evaluation/rag/evaluator.py`**（新增）：
  - `RagEvaluator.retrieve_and_answer(sample) -> RetrievalContext + answer`
  - `RagEvaluator.to_deepeval_test_cases(samples, contexts, answers) -> list[LLMTestCase]`
  - `RagEvaluator.evaluate(samples, config) -> RagEvalReport`（含反思轮数记录）
  - `RagEvaluator.evaluate_ab_reflection(samples) -> dict`（反思开/关对比）

### C. 新增 Agent 评测模块

- [ ] **`app/evaluation/agent/__init__.py`**（新增）：导出 `AgentEvaluator`、`AgentEvalReport`、`AgentTask`
- [ ] **`app/evaluation/agent/models.py`**（新增）：
  - `AgentTask`：`id/task/prd_input/expected_key_points/rubric/expected_max_iterations`
  - `ProcessMetrics`：`completed/iterations/human_review_required/retrieval_count/duration_s/total_cost`
  - `AgentEvalReport`：`summary/tasks(list[AgentTaskScore])/timestamp`
- [ ] **`app/evaluation/agent/evaluator.py`**（新增）：
  - `AgentEvaluator.run_task(task) -> ProcessMetrics + 结果`
  - `AgentEvaluator.judge_result(task, result) -> dict`（rubric 打分，结构化 JSON 解析）
  - `AgentEvaluator.evaluate(tasks) -> AgentEvalReport`

### D. 新增 CLI 脚本

- [ ] **`scripts/run_rag_eval.py`**（新增）：
  - 参数：`--dataset`、`--variant`、`--ab-reflection`
  - 加载数据集 → 跑 `RagEvaluator` → 写 `tests/eval/reports/rag_eval_<ts>.json` → 打印汇总
- [ ] **`scripts/run_agent_eval.py`**（新增）：
  - 参数：`--dataset`
  - 加载数据集 → 跑 `AgentEvaluator` → 写 `tests/eval/reports/agent_eval_<ts>.json` → 打印汇总

### E. 新增数据集与报告目录

- [ ] **`tests/eval/datasets/rag_qa.json`**（新增）：10-20 条，基于 `sample_prd.md`
- [ ] **`tests/eval/datasets/agent_tasks.json`**（新增）：3-5 条复杂生成任务
- [ ] **`tests/eval/reports/.gitkeep`**（新增）；建议 `tests/eval/reports/` 加入 `.gitignore`

### F. 新增测试

- [ ] **`tests/unit/test_rag_eval.py`**（新增）：mock `RetrievalPipeline` + LLM，断言指标计算与报告结构
- [ ] **`tests/unit/test_agent_eval.py`**（新增）：mock 图执行 + judge LLM，断言过程指标与 judge 解析
- [ ] **`tests/eval/`** 冒烟：真实跑 `run_rag_eval.py`（需配置 judge/embedding API key）

### G. 文档与记录

- [ ] **`overview.md`**：追加本块实现记录（R9a）
- [ ] **`README.md`**（如需）：评测使用方式一节（R9b）

### H. 验证

- [ ] Lint：`ruff check app/evaluation scripts tests` 
- [ ] 类型：`mypy`（如配置）
- [ ] 单测：`pytest tests/unit/test_rag_eval.py tests/unit/test_agent_eval.py`
- [ ] 冒烟：`python scripts/run_rag_eval.py` 真实跑通并输出报告
- [ ] 反思 A/B：跑 `--ab-reflection`，结论写入 `overview.md`

---

## 12. 潜在影响与风险

- **依赖风险**：deepeval 4.x 将 `click` 钉在 `<8.4.0`，与 `huggingface-hub>=8.4.2` 冲突（实测运行时不受影响，`pip check` 会告警）；升级 deepeval 时需复核
- **成本**：评测需真实 LLM 调用（judge + 回答 + deepeval 评判），有 token 成本；用 `--variant` 控制次数
- **隔离**：评测模块独立，不改现有检索/生成主逻辑，不接入运行时 API
- **数据质量**：黄金数据集是评测可信度上限，标注需谨慎；起步量小、后续可扩充
- **兼容**：`RetrievalContext` 字段稳定（`query/mode/results/total_tokens` 等），评测器只读取不修改；`community_summary` 字段名以 WP3 定稿为准（可能更名 `global_summary`）

---

## 13. 待确认点

1. ✅ 评测入口：CLI 脚本（不加 API）— 已确认
2. ✅ 反思 A/B：只验证不改逻辑 — 已确认
3. ✅ 数据集起步量：RAG 10-20 条 / Agent 3-5 条 — 已确认
4. ✅ 评测框架：deepeval 4.1.8（2026-08 迁移，替代 ragas 0.4.3）
