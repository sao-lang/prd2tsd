# 实施总方案：全链路追踪完善 + RAG/Agent 评测 + 社区检测简化

> **AI Summary**: 三个工作包的整体实施计划与逐文件 Checklist。
> - **WP1**：OpenTelemetry 全链路追踪 + Prometheus 指标完善（让链路可观测、指标真实记录）
> - **WP2**：RAG + Agent 评测体系（引入 ragas，详见 `docs/block-H-evaluation.md`）
> - **WP3**：社区检测/社区报告逻辑简化删除（Global Search 保留轻量实现）
>
> 实施顺序：**WP1 → WP3 → WP2**（先让观测可用、检索行为干净，再做评测闭环）。

---

## 总览

| 工作包 | 目标 | 状态 | 详细设计 |
|--------|------|------|---------|
| WP1 追踪 + 指标 | 链路从 HTTP 贯穿节点→LLM；Prometheus 业务指标真实记录 | 待实施 | 本文 §1 |
| WP2 评测 | RAG/Agent 评测可用并可反哺优化 | 待实施 | `docs/block-H-evaluation.md` |
| WP3 社区检测简化 | 删除未兑现的社区检测/报告逻辑 | 待实施 | 本文 §3 |

---

# WP1：OpenTelemetry 全链路追踪 + Prometheus 完善

## 1.1 现状问题

| 现状 | 问题 |
|------|------|
| `TracingMiddleware.wrap_node/wrap_async_node` 已定义 | 编排器/各 Layer 节点**未包装**，节点级 span 缺失 |
| LLM Gateway `complete()/stream_complete()` 有 OTel span | `track_llm_call` **从未被调用**，Prometheus 业务指标为空 |
| `LLM_CALL_TOTAL` 用 `Gauge` 定义 | 计数指标类型错误，应为 `Counter` |
| `/api/v1/metrics` + `prometheus.yml` 已就绪 | 无 HTTP 根 Span；Grafana 未在 docker-compose |
| `task_manager.py` 有完整任务生命周期 | 无任务指标埋点（TASKS_TOTAL/TASKS_DURATION） |

## 1.2 目标

- 链路追踪：**HTTP 请求 → 编排器节点 → LLM 调用** 形成完整 trace 树，Jaeger 可按 task_id 查看任务执行全过程
- 指标：`llm_calls_total` / `llm_latency_seconds` / `llm_tokens_total` / `llm_cost_total_usd` / `tasks_total` / `tasks_duration_seconds` 真实记录
- 查看入口：Jaeger UI（`http://localhost:16686`）、Prometheus（`http://localhost:9090`）、Grafana（新增）

## 1.3 逐文件 Checklist

### A. 观测性基础修复

- [ ] **`app/observability/metrics.py`**
  - [ ] `LLM_CALL_TOTAL` 由 `Gauge` 改为 `Counter`
  - [ ] （可选）新增 `HTTP_REQUESTS_TOTAL`（Counter，labels: method/path/status）、`HTTP_REQUEST_DURATION`（Histogram）
- [ ] **`app/observability/tracing.py`**
  - [ ] 新增 `http_tracing_middleware(request, call_next)`（FastAPI `@app.middleware("http")` 形态），创建 root span，attributes: `http.method/http.path/http.status/user_id`，异常时 `record_exception`
  - [ ] 新增 `trace_node(node_name)(fn)` 统一包装器：内部用 `inspect.iscoroutinefunction(fn)` 自动选择 `wrap_node`（同步）或 `wrap_async_node`（异步），避免人工判断同步/异步节点

### B. LLM Gateway 指标埋点

- [ ] **`app/llm_gateway/__init__.py`**
  - [ ] `complete()`：用 `with track_llm_call(model_name, layer, node) as token_info:` 包裹实际调用；成功路径写 `token_info["input_tokens"]/["output_tokens"]`
  - [ ] `stream_complete()`：同样接入 `track_llm_call`（流式结束后统计 token）
  - [ ] 在 `cost_tracker.record` 处补 `LLM_COST_TOTAL.labels(model_name).inc(response.cost)`
  - [ ] `all_calls_failed` / 护栏拦截 / 缓存命中路径也记录调用次数（避免指标低估）

### C. 任务指标埋点

- [ ] **`app/task_manager.py`**
  - [ ] `create_task`：`TASKS_TOTAL.labels("created").inc()`
  - [ ] `_execute_task` 成功/失败分支：`TASKS_TOTAL.labels("completed"/"failed").inc()` + `TASKS_DURATION.observe(duration)`

### D. 节点追踪（节点级 span）

- [ ] **`app/orchestrator/main_graph.py`**：`build_orchestrator_graph` 中所有 `graph.add_node(name, node.run)` → `graph.add_node(name, trace_node(name)(node.run))`
- [ ] **`app/analysis_layer/agent_graph.py`**：同上（注意 `parse_node`/`result_assembler` 是**同步** `def run`，由 `trace_node` 自动走 `wrap_node`）
- [ ] **`app/planning_layer/agent_graph.py`**：同上
- [ ] **`app/generation_layer/agent_graph.py`**：同上
- [ ] **`app/evaluation/agent_graph.py`**：同上
- [ ] 注意：`evaluation/agent_graph.py` 的 `Send()` 扇出与 `generation_layer` 的 `fan_out_sections` 均为**条件入口函数，不包装**；`trace_node` 按 `iscoroutinefunction` 自动选 sync/async 包装，避免漏包/错包

### E. HTTP 根 Span

- [ ] **`app/main.py`**：用 `@app.middleware("http")` 注册 `http_tracing_middleware`，使每个 `/api/v1/*` 请求成为 trace 根

### F. 部署：Grafana

- [ ] **`docker-compose.yml`**：新增 `grafana` 服务（`grafana/grafana:latest`，端口 `3000`，挂 `prometheus` 数据源）
- [ ] **`prometheus.yml`**：确认 scrape 目标含 `api:8000/api/v1/metrics`（已有）
- [ ] （可选）新增 `storage/grafana/dashboards/*.json`：LLM 调用 / 任务指标面板

### G. 测试与验证

- [ ] **`tests/unit/test_observability.py`** 扩展：
  - [ ] `LLM_CALL_TOTAL` 为 Counter 后断言 `.inc()` 生效（现有 4 用例用 `._value.get()` 断言，Counter 兼容无需改）
  - [ ] mock LLM Gateway 调用 `complete()` 后 `llm_calls_total` / `llm_latency_seconds` / `llm_tokens_total` 变化
  - [ ] `http_tracing_middleware` 生成 root span（mock tracer 断言）
- [ ] 冒烟验证：
  - [ ] 起服务 → 触发一次任务 → `curl localhost:8000/api/v1/metrics` 见 `llm_calls_total`/`tasks_total` 非零
  - [ ] Jaeger UI 可见 `http.* → node.* → gateway.complete.*` 完整 trace 树

## 1.4 潜在影响

- 节点包装通过 `functools.wraps` 保持签名/行为不变；异常照常抛出
- 指标新增标签不影响既有查询；Grafana 新增服务需 `docker compose up -d`
- LLM 每次调用增加极少开销（计数器 + 计时），可忽略

---

# WP2：RAG + Agent 评测（引入 ragas）

> 完整详细设计见 **`docs/block-H-evaluation.md`**（指标分层 / 数据集 schema / 模块设计 / 脚本 / 反思 A/B / 优化闭环）。

## 2.1 Checklist 摘要（详见 block-H §11）

- [ ] **依赖**：`requirements.txt` + `pyproject.toml` 加 `ragas`（先验证与 langchain-core 0.3 / langgraph 1.2 兼容，锁版本）
- [ ] **RAG 评测模块**：新增 `app/evaluation/rag/{__init__,models,dataset_loader,evaluator}.py`
- [ ] **Agent 评测模块**：新增 `app/evaluation/agent/{__init__,models,evaluator}.py`
- [ ] **CLI**：新增 `scripts/run_rag_eval.py`（`--variant`/`--ab-reflection`）、`scripts/run_agent_eval.py`
- [ ] **数据集**：`tests/eval/datasets/rag_qa.json`（10-20 条）、`agent_tasks.json`（3-5 条）、`reports/` 目录
- [ ] **测试**：`tests/unit/test_rag_eval.py`、`tests/unit/test_agent_eval.py`（mock）+ 冒烟
- [ ] **文档**：`overview.md` 记录、README 评测用法

---

# WP3：社区检测 / 社区报告简化删除

## 3.1 现状

| 现状 | 问题 |
|------|------|
| PRD 设计了 Leiden 社区检测（`prd2tsd.prd.md` §3.2.2） | **实际未实现**，无 igraph/leidenalg 依赖 |
| `global_search.py` 用 `_generate_base_reports` 按实体类型分组生成伪社区报告 | 社区检测/报告是"未兑现的复杂逻辑" |
| `CommunityReport` 模型（`models.py`） | 仅被 `global_search.py`/`pipeline.py` 使用 |
| `GlobalSearchResult` 含 `reports/level` 字段 | 增加不必要复杂度 |

## 3.2 目标（选 A：保留 Global Search 骨架，删社区检测层）

- 删除：`CommunityReport`、`_get_community_reports`、`_generate_base_reports`、`_select_level`、`GlobalSearchResult.reports/level`
- 保留：Global Search 的"宏观总结"价值 → 简化为 **实体按类型聚合 + LLM 宏观总结**
- hybrid/global 模式继续可用，"整体架构"类查询仍返回宏观总结

## 3.3 逐文件 Checklist

- [ ] **`app/knowledge_layer/models.py`**
  - [ ] 删除 `CommunityReport` 类
  - [ ] `RetrievalContext.community_summary` 字段名 → `global_summary`（或沿用，见 pipeline 项，推荐改名为 `global_summary` 语义清晰）
- [ ] **`app/knowledge_layer/retrieval/global_search.py`**
  - [ ] 删除 `_get_community_reports` / `_generate_base_reports` / `_select_level`
  - [ ] `GlobalSearchResult` 去掉 `reports`/`level`，只留 `answer`
  - [ ] `search()` 简化为：`get_all_entities` → 按 `entity.type` 聚合 → `_summarize`（保留 `COMMUNITY_SUMMARY_PROMPT`，或更名 `GLOBAL_SUMMARY_PROMPT`）
  - [ ] `search_as_docs()` 改为基于实体聚合生成 `ScoredDoc`（source="global"）
- [ ] **`app/knowledge_layer/retrieval/__init__.py`**
  - [ ] 导出保持 `GlobalSearch`（导出列表不变），更新模块 docstring
- [ ] **`app/knowledge_layer/pipeline.py`**
  - [ ] 删除 `CommunityReport` import
  - [ ] `retrieve()` 中 `community_summary` 字段引用改为新字段名
  - [ ] global/hybrid 分支适配新的 `GlobalSearchResult`
- [ ] **`app/orchestrator/nodes/retrieve_node.py`**：`retrieval_result.community_summary` → 新字段名（第 87-88 行）
- [ ] **`app/api/routes/stream_qna.py`**：`retrieval_result.community_summary` → 新字段名（第 68-69 行）
- [ ] **`app/knowledge_layer/interfaces.py`**
  - [ ] 更新"不可替换层"注释（GlobalSearch 描述去掉社区报告）
- [ ] **测试**
  - [ ] `tests/unit/test_global_search.py`：删除社区报告相关断言，改为验证"实体聚合 + 宏观总结"
  - [ ] `tests/integration/test_global_search_integration.py`：同步更新
- [ ] **文档**
  - [ ] `docs/block-B-knowledge-layer.md`：更新 Global Search 章节（§1 核心功能 9、§2 目标表、§9.5 测试）
  - [ ] `docs/full-architecture-deep-dive.md`：同步 Global Search 描述
  - [ ] `prd2tsd.prd.md`：§3.2.2 社区检测设计标注"已简化/未实现"
- [ ] **验证**
  - [ ] 单测：`pytest tests/unit/test_global_search.py tests/integration/test_global_search_integration.py`
  - [ ] 冒烟：`RetrievalPipeline.retrieve("这个项目的整体架构", mode="global")` 仍返回宏观总结

## 3.4 潜在影响

- 按类型聚合的宏观总结能力弱于社区报告（但当前伪社区报告本来也是按类型分组），**质量基本持平**
- 未来若要上 GraphRAG（真社区检测），需重新实现；`interfaces.py` 已预留替换边界
- 删除均基于用户明确要求（R5 豁免场景）

---

# 实施顺序与验证

```
WP1 追踪+指标（观测地基）
  → WP3 社区检测简化（检索行为干净）
    → WP2 评测闭环（依赖前两者稳定）
```

| 阶段 | 入口 | 验收 |
|------|------|------|
| WP1 | 全链路可观测 | Jaeger 见完整 trace；metrics 非零；单测通过 |
| WP3 | 检索简化 | global 模式可用；相关单测通过 |
| WP2 | 评测闭环 | `run_rag_eval.py` 真实跑通出报告；反思 A/B 有结论 |

统一验证：每 WP 完成 → `ruff check` + `mypy` + 相关 pytest → 冒烟 → 结果按 `03-testing` 模板报告。

---

# 待确认点

1. ✅ WP3 选 A（保留骨架，删社区检测层）
2. ✅ 评测入口 CLI、不加 API
3. ✅ 反思只做 A/B 验证、不改逻辑
4. ✅ 数据集起步量：RAG 10-20 / Agent 3-5
5. ⏳ `ragas` 兼容版本：实施 WP2 第一步实测后锁定
6. ⏳ WP1 中 `RetrievalContext.community_summary` 是否改名为 `global_summary`：默认改；**影响 4 个代码文件**（`models.py` / `pipeline.py` / `orchestrator/nodes/retrieve_node.py` / `api/routes/stream_qna.py`），WP3 一并处理
