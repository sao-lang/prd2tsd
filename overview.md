# PRD2TSD Agents — 开发记录

### 2026-08-18

#### 34. 面试文档二轮优化：修正过时状态 + 新增速查卡 / STAR / 自测列 / 证据映射

- **时间：** 2026-08-18
- **发起人：** user（“全部一起做完吧”）
- **依据：** 面试文档全量通读 + 与代码 / 实测逐项核对
- **修改内容：**
  1. **过时内容修正**：§7.5 “143 文件未提交”删除（工作区已干净）；§5.17 P1 移除已完成项（阈值配置化 / RuntimeInjector / BatchTask 落库，条目 31）；§8 Q28 已知问题改为当前边界；§6.4 反思轮数描述修正（pipeline 已记录 last_reflection_rounds，evaluator 仍读配置值）；SSRF 用例数 11 → 21（4 处）。
  2. **interview-questions.md**：版本升 v1.1（2026-08-18）；“仍可扩展”移除 2 项已完成项并并入“已实现”。
  3. **新增内容**：§1.4 简历说法 ↔ 代码证据映射；§8.1 两个 STAR 故事（并行写冲突、评测闭环 mock 验证）；§8 速查表加“自测”打勾列；§9.5 考前 30 分钟一页纸速查卡。
- **复盘结果：** 全量核对后无遗留旧数字（SSE 事件类型实测 20 种，“15+”表述仍成立）；纯文档变更，未改代码。
- **潜在风险：** 无（文档一致性已复核）。

#### 33. 面试/架构文档勘误：主编排节点数 16 + 测试数字实测更新

- **时间：** 2026-08-18
- **发起人：** user（“首先把问题修掉”）
- **依据：** 面试准备前的文档与代码逐项核对（上一轮审查结论）
- **修改内容：**
  1. **主编排节点数 15 → 16**：入口节点 `inject_runtime`（线程级注册表，条目 31 接线）此前未计入节点清单 / 拓扑 / 速查表；同步修正 full-architecture-deep-dive、interview-prep-complete、interview-questions。
  2. **测试数字统一为实测值**：`pytest tests/unit`（2026-08-18 本机实测）＝ 357 过 / 1 败（test_batch 需 Redis）/ 18 error（DB 依赖用例需本地 PostgreSQL）；overview 条目 32 记录的完整环境基线 380 过 / 1 败保留为历史基线并注明环境；代码规模更新为 app 262 文件 / 约 2.25 万行。
  3. **过时描述修正**：文档搜索“语义向量占位未实现”→ 已实现（条目 31）；save_session“仅发 SSE 未落库”→ 已落库 sessions/session_messages（条目 29 / 2026-07-28）。
- **复盘结果：** 面试手册 §8 速查表复核后确认结构正常（此前误读为“前 8 行是已知问题表”），无需修改；其余数字修正均已对照代码 / 实测验证。
- **潜在风险：** 集成 54 / 冒烟 4/4 / lint+tech-stack 7 为本机未复跑的基线数字，面试前应起 Docker 环境复核。

### 2026-08-16

#### 32. RAG 评测框架迁移：ragas 0.4.3 → deepeval 4.x

- **时间：** 2026-08-16
- **发起人：** user（"使用DeepEval"）
- **依据：** ragas 0.4.3 与 langchain 1.x / Python 3.14 不兼容（import 需 shim、metrics 导入为模块导致 TypeError、事件循环内 nest_asyncio 收尾崩溃）；PyPI ragas 最新版仍为 0.4.3，无可用升级路径
- **修改内容：**
  1. **依赖替换**：`requirements.txt` / `pyproject.toml` 中 `ragas==0.4.3` → `deepeval>=4,<5`（实测安装 4.1.8，Python 3.14 可用）
  2. **evaluator.py 重写**：`to_ragas_dataset` → `to_deepeval_test_cases`（LLMTestCase：input/actual_output/expected_output/retrieval_context）；四指标映射 Contextual Precision/Recall ↔ context_precision/recall、Faithfulness/Answer Relevancy；judge 用 OpenAIModel 注入项目 judge 配置；`evaluate_async` 改用 `asyncio.to_thread` 规避 nest_asyncio 收尾崩溃
  3. **删除** `_compat.py`（ragas vertexai shim）及相关 `install_ragas_shims` 调用
  4. **测试更新**：test_rag_eval.py 适配 deepeval（7 例全过）
  5. **文档同步**：block-H 设计文档、README、tech-stack.yml、full-architecture、interview-questions、plan-observability-eval-cleanup、.gitignore（.deepeval/）
- **复盘结果：** 冒烟验证两条路径（同步 evaluate / 异步 to_thread）均打通到真实 API 调用；因 .env judge key 为占位符（sk-your-…）停在 401，配置有效 key 后可跑通
- **潜在风险：** deepeval 4.x 将 click 钉在 <8.4.0，与 huggingface-hub >=8.4.2 冲突（实测导入/运行正常，pip check 告警）；评测报告依赖有效 LLM API key
#### 31. 全量断点/硬编码整改（IterationDecider 配置化 + Runtime 接线 + 语义搜索 + 批量任务落库等 11 项）

- **时间：** 2026-08-16
- **发起人：** user（"把所有发现的问题全部修复完"）
- **依据：** 代码审计（硬编码/占位实现/功能断点扫描）+ 架构文档第 21 章
- **修改内容：**
  1. **IterationDecider 阈值配置化**：注入 OrchestratorConfig（pass=85/replan=70/max_iterations=3），顺带修复中段维度判断第 3 个硬编码 70；`build_and_compile` 的 config 死参数打通；`make_initial_state` 的 max_iterations 默认值改从 Config 取（显式传参仍可覆盖）。
  2. **RuntimeInjector 安全接线**：`OrchestratorRuntime` 实测不可被 checkpoint 序列化（msgpack），改为线程级注册表（register/get/unregister），主编排图新增入口节点 inject_runtime；chat/retrieve/clarify 节点读取注册表（保留全局兜底）；save_session/clarify 节点任务结束注销。
  3. **文档搜索语义路实现**（原占位）：向量块表加 document_id 列（运行时建表 + Alembic 迁移 f3a4b5c6d7e8）；build_from_text/build_from_bytes 透传 document_id；上传入图任务写入文档 ID；DocumentSearchService 增加语义检索（查询向量→块相似度→按文档聚合）+ FTS/语义融合去重。
  4. **修复 similarity_search 重复执行 bug**：同一查询 execute 两次（第二次无参数必报错），删除冗余执行。
  5. **BatchTaskService 落库**：新增 batch_tasks 表 + ORM BatchTask，DB 不可用降级内存（与 TaskManager 同策略）。
  6. **死配置清理**：OrchestratorConfig 删除 max_llm_retries/keepalive_interval/session_ttl_days（零消费；keepalive 由 sse.py 常量负责、会话 TTL 由 SessionCleanupPolicy 负责）。
  7. **TokenResponse 去重**：统一由 api/schemas/response 定义，auth/models 复用导出。
  8. **熔断默认值对齐**：failure_threshold 默认 5→3（与 gateway 调用与文档一致）。
  9. **反思轮数占位修复**：RetrievalPipeline 记录 last_reflection_rounds，ragas 评测读取实际轮数。
- **修改文件：** 17 个 app 文件 + 1 个迁移（f3a4b5c6d7e8）+ 3 个新测试
- **Lint/类型：** ✅ ruff All checks passed；mypy 17 文件 Success: no issues found
- **测试：** ✅ 全量单元 380 过 / 1 败（test_batch 需 Redis broker，既有环境依赖）；新增 11 例（迭代决策 5 + Runtime 注册表 3 + 语义搜索 3）
- **复盘结果：** 审计再确认"初始化≠被调用"仍是主要病根（OrchestratorConfig 全字段零消费、similarity_search 重复执行）；Runtime 注入必须先验证序列化能力再接线
- **潜在风险：** 迁移需在真实 Postgres 执行 `alembic upgrade head`；batch_tasks/document_id 为增量列（既有数据 document_id 为空，需重跑入图才可被语义搜索命中）；文档搜索语义路依赖 embedding API key

### 2026-08-15

#### 30. CR 防回归机制 Phase 0-1：四道闸门基线清零 + 存量清剿

- **时间：** 2026-08-15
- **发起人：** user（"按照文档开始任务"）
- **依据：** docs/plan-cr-mechanism.md（四道机器闸门 + 基线清单 + 闭环约定）
- **修改内容：**
  - **Phase 0 基线采集**：ruff 6 条、mypy 205 条（72 文件）、单元 359 过 1 败 2 错、集成 47 过 7 败，生成 docs/known-issues.md
  - **ruff 清零**：未用导入、SIM108 三元、行超长、冗余同步测试
  - **mypy 清零（205→0）**：dict/StateGraph/BaseCheckpointSaver 泛型参数、no-any-return、no-untyped-def、未用 type:ignore、连接器 None 类型、TypedDict 部分返回、SQLAlchemy CursorResult rowcount、result 变量复用推断错乱等
  - **真实 bug 修复（均带回归测试）**：Evaluation 并行扇出 InvalidUpdateError（只返回增量）；Planning 自检无限递归（attempts 上限=3）；GuardrailResult 缺 name 字段；HealthResponse.model_config 被 Pydantic 吞掉（alias 保持 API 形状）；KnowledgeGraphBuilder.get_stats/cleanup_expired 不存在（实现 + 重写清理任务）；BuildStats 缺 relations；SessionMessage.attachments 类型标注错误
  - **测试修复**：IntegrationHub 5 项 async 未 await；test_lint 46 处缺 docstring；新增 scripts/check_tech_stack.py（基于 tech-stack.yml 黑名单）替代 grep 式 CI job；CI 补 redis service、alembic upgrade、Python 3.12 对齐
  - **环境验证**：Postgres(5433)/Redis(6379)/Neo4j(7701)/MinIO(9002 验证容器) 真实冒烟全绿；E2E 待 LLM key 按约定跳过
- **修改文件：** app/ 约 100 文件 + tests/ 约 15 文件 + scripts/ + .github/workflows/ci.yml + docs/known-issues.md（新增）
- **Lint/类型：** ✅ ruff `All checks passed!`；mypy `Success: no issues found in 266 source files`
- **测试：** ✅ 单元 368 过 / 集成 54 过 / test_lint + tech-stack 7 过 / 真实环境 Smoke 4/4 通过
- **复盘结果：** 根因符合方案 R1-R4（审查靠自觉、问题不沉淀、修复无回归、门禁与现状脱节）；mypy 需清缓存后全量重跑，增量缓存会产生假错误
- **潜在风险：** E2E 需 LLM key；prd2tsd-minio 未发布端口（验证用独立容器）；docs/known-issues.md 后续需脚本化校验（Phase 2 cr_toolkit）；BatchTaskService 仍内存存储

### 2026-08-14

#### 29. 功能断点全量整改（18 项：记忆/SSE/回放/评分/脱敏/持久化）

- **时间：** 2026-08-15
- **发起人：** user（"先解决你检查出来的问题吧"→"按方案全做"）
- **依据：** 全库审查实测断点清单（6 🔴 + 11 🟡 + 4 🔵）
- **修改内容：**
  - **P0 管道断裂（5 项）**：SaveSessionNode 真正落库（会话+双消息+摘要，thread_id 绑定 task_id）；chat/clarify/retrieve 节点 SSE 回退全局 EventBus；WebIndexer 悬空导入改 WebSyncScheduler；记忆链路打通（State 增 session_id/历史/记忆字段，interact/task_manager 传 session_id，retrieve/compress/chat 节点注入与消费）；DecisionRecorder 单例化 + 4 适配器与 2 节点补 record_decision
  - **P1 半实现（9 项）**：EVENT_TYPES 补 7 项；MemoryRetriever 时间戳/向量相关性；BuildStats.claims；ScoringNode 显式 DIM_WEIGHTS + ScoreCalibrator 历史落库（evaluation_scores 表）；ImplementabilityEvalNode 改读 planning_result.metadata；DataMaskingEngine 可逆脱敏接入 gateway；TaskManager 落库（task_runs，重启可恢复断点）；Webhook 注册落库（webhook_subscriptions）；迁移/ORM 对齐 + tech-stack.yml 修正
  - **P2 死代码（4 项）**：删除 app/agents 与 app/core/prompt_registry 及其测试；UnifiedImageEncoder 确认已不存在；死配置清理
- **修改文件：** app/orchestrator|session_history|evaluation|security|llm_gateway|integrations|batch|models|api/routes 等约 35 文件 + alembic 迁移 e1f2g3h4i5j6 + 8 个新测试
- **Lint/类型：** ✅ ruff 改动文件全绿；mypy 改动文件无新增错误
- **测试：** ✅ 新增接线断言 10 例 + 修正 3 个受影响既有测试；全量单元 355 过 / 4 败（test_batch 需 Redis 为既有环境依赖；2 个 test_ingestion 为本机 tmp_path 权限）
- **复盘结果：** 用运行时证据+递归检索复核，纠正上轮 1 处误报（Checkpointer 实际已接线）；断点根因仍是"组件初始化≠被调用、注释先于实现、无接线断言测试"
- **潜在风险：** 迁移需在真实 Postgres 执行 `alembic upgrade head`；TaskManager 落库依赖 task_runs 表，DB 不可用时降级内存；BatchTaskService 仍内存；RuntimeInjector/IterationDecider 阈值/TokenResponse 重复定义待后续处理

#### 28. 代码审查修复：evaluate/文档搜索两处 500 + Postgres checkpointer 用法错误

- **时间：** 2026-08-15
- **发起人：** user（"审查" → 确认实施修复）
- **依据：** 全库审查实测复现的 3 个问题
- **修改内容：**
  - **`POST /api/v1/evaluate` 500**：`evaluate.py` 在请求不带 `analysis_result` 时构造 `AnalysisResultDetail()`，缺必填字段 `project_name`/`summary` 抛 ValidationError。修复为 `AnalysisResultDetail(project_name="", summary="")`，并给 `input_state` 补类型注解
  - **`GET /api/v1/documents?q=...` 500**：搜索分支返回 `SearchResultItem`，但 `DocumentListResponse.items` 声明为 `list[DocumentResponse]`，FastAPI 响应序列化失败。修复为 `list[DocumentResponse | SearchResultItem]`（`SearchResultItem` 定义上移）
  - **`create_postgres_checkpointer()` 用法错误**：`PostgresSaver.from_conn_string()` 返回上下文管理器，原代码直接 `.setup()` 必抛 AttributeError。修复为 `with ... as checkpointer` 内建表并返回；依赖补 `psycopg[binary]>=3.2.0`（纯 psycopg 缺 libpq 无法导入）
  - 新增回归测试 `tests/unit/test_evaluate_route.py`（2 例）、`tests/unit/test_documents_route.py`（2 例，搜索/列表两分支）
- **修改文件：** `app/api/routes/evaluate.py`、`app/api/schemas/document.py`、`app/orchestrator/main_graph.py`、`requirements.txt`、`pyproject.toml`、`tests/unit/test_evaluate_route.py`（新增）、`tests/unit/test_documents_route.py`（新增）
- **Lint/类型：** ✅ ruff 改动文件全绿；mypy 对应错误（evaluate call-arg、documents misc、checkpointer attr-defined/return-value）全部消除，剩余为既有泛型参数噪音
- **测试：** ✅ 新增回归 4 例 + 文档管理既有用例共 16 过；两个 500 修复均经运行时探针复现验证
- **复盘结果：** 两个 API 500 无测试覆盖故存活至今；checkpointer 错误为 mypy 报错但函数未接线未被触发。根因均为"类型/接口契约与实际返回不一致"
- **潜在风险：** `DocumentListResponse.items` 改为联合类型后，OpenAPI 响应 schema 变为 union；`create_postgres_checkpointer` 仍未被 deps 接线（生产断点持久化尚未启用，见架构文档第二十一章）

#### 27. 架构文档补齐缺失链路（可追踪链路等 5 条）

- **时间：** 2026-08-14
- **发起人：** user（"你确定所有链路都有了吗？我没看到可追踪链路"）
- **依据：** 用户审查反馈——文档第八章仅有追踪模块实现细节，缺完整"可追踪链路"
- **修改内容：** `docs/full-architecture-deep-dive.md` 新增 5 条链路小节
  - **8.6 可追踪链路**（重点）：span 生成与传播（http 根 span → node 节点 span → gateway CLIENT span → BatchSpanProcessor → OTLP gRPC → Jaeger），含 trace 树示例、attributes 清单、按 task_id 检索方式、**异步任务 trace 特性说明**（asyncio.create_task 复制 contextvars、HTTP 根 span 早于任务结束 → 按 task_id 检索最可靠）；指标链路（埋点 → /api/v1/metrics 暴露 → Prometheus scrape → Grafana 展示）
  - **2.8 认证授权链路**：注册/登录/刷新/登出 + 请求鉴权（AuthMiddleware → WorkspaceContextMiddleware → http tracing → require_permission → TenantContext）
  - **3.12 知识图谱构建链路**：文档上传/URL/路径三条入口 → 多格式提取 → 分块 → 实体 → 消歧 → embedding → 双写 Neo4j+PGVector → Claims → 状态跟踪
  - **3.13 检索链路**：四条查询入口 → IntentRouter → Rewriter → Enricher → 反思循环（Local/Global/RRF）→ ReRanker → Compressor → RetrievalContext → 消费方
  - **6.9 文档上传 → 入图链路**：上传 → 校验/去重 → MinIO → DB → Celery 异步入图 → 状态更新 → 查询消费
  - 更新文档结尾"覆盖"声明（全链路清单加入可追踪/认证/构建/检索/文档入图）
- **修改文件：** `docs/full-architecture-deep-dive.md`、`overview.md`（本条）
- **复盘结果：** 文档"链路章节"此前只有 7 条用户请求类链路（主线/对话/问答/文档/断点/历史/SSE/LLM），横切链路（追踪/认证）与数据类链路（构建/检索/入图）缺失；本次按"链路 = 有头有尾的数据流"标准补齐
- **潜在风险：** 8.6 异步任务 trace 特性为实测观察（create_task 复制 contextvars），Jaeger 实际呈现取决于任务创建时机；如后续修复 RuntimeInjector，SSE 副作用链路需同步更新

#### 26. 架构文档全链路重写（v3.0）+ 面试专题迁移

- **时间：** 2026-08-14
- **发起人：** user（"更新这个文档…需要全链路…去掉面试相关的章节另开一个文档"）
- **依据：** 探索代码库实际状态（overview 25 之前的全部演进均已落地）
- **修改内容：**
  - **重写 `docs/full-architecture-deep-dive.md`（4287 行 → 1987 行，v3.0）：** 基于 2026-08-13 代码库真实状态全量重写，覆盖所有功能模块与运行时链路
    - 修正过时信息：ToolRegistry 工具系统已废弃标注；6 个已删端点（/chat、/generate、/qna/stream 等）统一为 /interact；社区检测已简化（community_summary→global_summary）；Send() 并行扇出已实现（Evaluation 9 节点 + Generation fan_out_sections）；docker 拓扑（grafana/PG15/neo4j 7700）；DB 表（10 张，无 documents/web_resources 表）
    - 新增章节：八（评测与观测 WP1/WP2）、十一（document_analysis/URL 链路）、二十一（已知问题与风险 18 项，基于实测）
  - **新建 `docs/interview-questions.md`：** 迁移原第十七章（核心卖点）+ 附篇 I（业界对比）+ 附篇 J（问答模板），并基于代码现状更新（Send 已实现/工具已废弃/统一入口/评测闭环），新增 Q9 评测体系、Q10 数据脱敏
- **修改文件：** `docs/full-architecture-deep-dive.md`（重写）、`docs/interview-questions.md`（新建）、`overview.md`（本条）
- **Lint/类型：** N/A（纯文档）
- **复盘结果：** 文档与代码不一致的根因是"演进记录分散在 overview 各条目，未回写架构文档"；本轮以代码为唯一真相源重写，并在文档中明确标注已知问题（RuntimeInjector 未接线/SaveSessionNode 未持久化/IterationDecider 硬编码/WebIndexer 悬空引用等）
- **潜在风险：** 新文档约 1987 行（原 4287 行），删除了重复/过时内容，信息密度更高但篇幅变小；若后续代码演进，需同步回写本文档；interview-questions.md 为独立文档，架构文档已移除面试章节

### 2026-08-13

#### 25. 观测性完善（WP1）+ 社区检测简化（WP3）+ RAG/Agent 评测（WP2）

- **时间：** 2026-08-13
- **发起人：** user（确认实施 `docs/plan-observability-eval-cleanup.md`）
- **依据：** `docs/plan-observability-eval-cleanup.md`（WP1→WP3→WP2 顺序）
- **修改内容：**
  - **WP1 全链路追踪 + Prometheus 指标：**
    - `metrics.py`：`LLM_CALL_TOTAL` Gauge→Counter；新增 `HTTP_REQUESTS_TOTAL`/`HTTP_REQUEST_DURATION`
    - `tracing.py`：新增 `trace_node()` 统一包装器（`inspect.iscoroutinefunction` 自动选 sync/async）+ `http_tracing_middleware`（HTTP 根 span，含 user_id 解析）；修复 `wrap_async_node` 误用 `async def` 的 bug
    - `llm_gateway/__init__.py`：`complete()`/`stream_complete()` 接入 `track_llm_call`（成功/缓存命中/失败路径均计数）；成本处补 `LLM_COST_TOTAL.inc`；修复 span `kind=1`（整数）导致 OTLP 导出 KeyError 的 bug
    - `task_manager.py`：`TASKS_TOTAL(created/completed/failed)` + `TASKS_DURATION.observe`
    - 5 个图文件（orchestrator/analysis/planning/generation/evaluation）所有 `add_node` 用 `trace_node` 包装（条件入口函数不包装）
    - `main.py` 注册 `@app.middleware("http")`；`docker-compose.yml` 新增 `grafana` + provisioning/dashboard；`conftest.py` 测试环境禁用 OTLP
  - **WP3 社区检测简化：** `global_search.py` 删社区检测/报告（`_get_community_reports`/`_generate_base_reports`/`_select_level`），简化为「实体按类型聚合 → LLM 宏观总结」；`CommunityReport` 删除；`RetrievalContext.community_summary`→`global_summary`（4 处：models/pipeline/retrieve_node/**interact.py**——plan 所述 `stream_qna.py` 已不存在）；文档同步（block-B/full-architecture/prd §3.2.2 标注简化）；顺带修复 `graph_store.py` `session.run(**params)` 含 `query` 键的参数冲突 bug
  - **WP2 RAG + Agent 评测（引入 ragas 0.4.3）：**
    - 验证 ragas 0.4.3 与 langchain-core 1.5.4 / langgraph 1.2.11 兼容；`_compat.py` shim 解决 `langchain_community.chat_models.vertexai` 缺失（langchain-community≥0.4 拆分）
    - 新增 `app/evaluation/rag/`（models/dataset_loader/evaluator：RagEvaluator，含反思 A/B）+ `app/evaluation/agent/`（models/evaluator：AgentEvaluator，L3 过程指标 + L4 rubric judge）
    - 新增 `scripts/run_rag_eval.py`（--dataset/--variant/--ab-reflection）、`scripts/run_agent_eval.py`
    - 黄金数据集 `tests/eval/datasets/rag_qa.json`（12 条）/`agent_tasks.json`（4 条）；依赖 `ragas==0.4.3`；`.gitignore` 忽略报告
- **修改文件：** WP1（observability/*、llm_gateway/__init__、task_manager、5 图文件、main、docker-compose、conftest、test_observability）+ WP3（knowledge_layer/{models,pipeline,graph_store,retrieval/*}、retrieve_node、interact、2 个 global_search 测试）+ WP2（app/evaluation/rag|agent、scripts/run_*_eval、tests/eval、tests/unit/test_rag_eval|test_agent_eval、requirements、pyproject、.gitignore、README）
- **Lint/类型：** ✅ ruff 改动文件全绿（全量 25 条为既有，非本次引入）；mypy 核心修改文件无新增错误
- **测试：** ✅ 全量单元 **359 过/1 败**（`test_batch` 需 Redis broker，预存在环境依赖，条目 23 同基线）；WP1 观测 8 过 + 图构建 24 过；WP3 global_search 6 过 + 知识层 15 过；WP2 评测 10 过 + **TaskManager 任务指标 4 过（新增）**；冒烟：Jaeger 见 `http.* → node.*` 完整 trace 树、metrics 非零、pipeline global 模式返回宏观总结、**评测闭环端到端跑通（数据集→检索→回答→评分→报告产出，mock 外部 LLM）**
- **复盘结果：** WP1 冒烟暴露 2 个预存在 bug（span kind=1 整数致 OTLP 导出崩溃、wrap_async_node 误用 async def），均已修复；WP3 冒烟暴露 graph_store `session.run` 参数冲突（阻塞检索管线），已修复；WP2 真实评测因 `.env` API key 为无效占位符（DeepSeek/OpenAI 均 401）未跑通，需配置有效 key 后执行；`total_tokens` 由硬编码 0 改为从 `RetrievalContext` 实读
- **潜在风险：** ragas 依赖较重且与 langchain-community 0.4 有 vertexai 兼容 shim（升级需复核）；`community_summary→global_summary` 为内部字段改名；评测报告依赖有效 LLM API key；Grafana 需 `docker compose up -d` 生效

#### 24. 块 E 整改复盘修复（doc_id 文档分析断点 + 集成测试 + 文档同步）

- **时间：** 2026-08-13
- **发起人：** user（"可以"确认 code-review 修复方案）
- **依据：** code-review 报告（`enterprise-feature-revamp-plan.md` 实现完整性审查）
- **修改内容：**
  - **功能断点修复（#1）：** `document_analysis` 意图经 `doc_id` 分析 PDF/docx/图片时原读预览占位文本（`[PDF 文件，大小 N 字节]`）而非正文。修复：`service.py` 新增 `get_document_content()`（下载原始字节），`interact.py::_load_document_text` 改用 `multi_format_loader.extract_text` 按格式提取真实内容，同时消除 CSV 预览前 20 行截断
  - **预览增强：** `preview.py` 新增 `_preview_docx`，`_preview_pdf` 复用 `multi_format_loader.extract_text`（解析失败降级占位），预览端点不再返回占位
  - **集成测试补齐（P3 未完成项）：** 新增 `tests/integration/test_interact_flow.py`（chat / knowledge_qa / complex_generation 三意图同步全流程 + 图异常 LLM 降级）；`test_interact.py` 新增 `TestLoadDocumentText`（断点回归：md/csv 全量提取、pdf 走 extract 非占位、不存在/提取失败降级）
  - **文档同步（R9b）：** 清理 `block-E-enterprise.md` E12 段、`block-D-orchestration.md`、`block-F-production-hardening.md`、`full-architecture-deep-dive.md`、`phase-prompts.md` 中已删除端点（`/api/v1/chat`、`/generate`、`/qna/stream`、`/generate/stream`、`stream_qna.py`）引用，统一指向 `/api/v1/interact`
- **修改文件：** `service.py`、`interact.py`、`preview.py` + 新增 `tests/integration/test_interact_flow.py`、改 `tests/unit/test_interact.py` + 5 份 docs
- **Lint/类型：** ✅ ruff 改动文件全绿
- **测试：** ✅ 整改相关 73 项全过（unit test_interact 19 + url_security + url_document + multi_format_loader + kg_build_multi_format + document_management）；全量单元回归待确认
- **复盘结果：** 断点根因是「多格式入图（build_from_bytes）与文档分析（preview）两条提取路径不一致」，符合历史"修复后未递归验证"漏检模式——本轮从分析端修复并补回归测试
- **潜在风险：** `_analyze_document` 仍截断 12000 字符（长文档分析不完整，可接受）；PDF/docx 分析依赖 pypdf/python-docx 安装；preview 增强对超大 PDF 有解析耗时

#### 23. 块 E 企业级功能整改（P0 删除 + P1 统一入口 + P2 URL + P2.5 多格式入图）

- **时间：** 2026-08-13
- **发起人：** user（"开始这个任务" → 分阶段验收）
- **依据：** `docs/enterprise-feature-revamp-plan.md`
- **修改内容：**
  - **P0 删除类（4 项）：** A1 删 CSV 双通路索引（`csv_loader.py`、`/csv-import`、`CsvImportResponse`）；A2 删 CLIP 多模态（`app/multimodal/`、路由/schema、`gateway.image_encoder`、`IMAGE_ENCODE_MODE`/`CLIP_MODEL_NAME`、Pillow）；A3 删协作文档（`app/collaboration/`、路由/schema）；A4 删搜索引擎回退（`search_fallback.py`、`/search-fallback`、`pipeline.py` 自动回退段）
  - **P1 统一交互入口（B1）：** 新增 `POST /api/v1/interact`（chat/knowledge_qa/document_analysis/complex_generation/clarification 分流 + 同步/流式双模式）；`IntentClassifier` 增 `document_analysis` 意图；classify 节点幂等化（消除双实现）；移除 `/chat`、`/generate`、`/qna/stream`、`/generate/stream`；新增 `app/streaming/sse.py` 共享 SSE 工具
  - **P2 URL 文档分析（B2）：** 新增 `url_security.py`（SSRF：协议白名单 + 内网拦截 + DNS 二次检查）、`url_document.py`（URL→抓取→入库 file_type=url+source_url）、`InteractRequest.generate` 一键生成 TSD
  - **P2.5 多格式入图（B3）：** 新增 `multi_format_loader.py`（pdf/csv/docx/md/txt/图片提取）、`KnowledgeGraphBuilder.build_from_bytes()`、Celery 任务 `index_document_to_kg`、`upload()` 后自动触发入图 + processing_status 状态跟踪；依赖加 `pypdf`
- **修改文件：** 新增 8（`interact.py`/`schemas/interact.py`/`streaming/sse.py`/`url_security.py`/`url_document.py`/`multi_format_loader.py` + 6 个测试）；删除 2 目录 + 9 文件（`multimodal/`、`collaboration/`、`chat.py`、`stream_qna.py`、`csv_loader.py`、`search_fallback.py`、相关 schema/测试）；修改 15+（`main.py`、`intent_classifier.py`、`intent_classify.py`、`state.py`、`documents.py`、`service.py`、`batch/tasks.py`、`knowledge_layer/pipeline.py`、`requirements.txt` 等）
- **Lint/类型：** ✅ ruff 改动文件全绿；mypy 无新增错误（基线 195 条既有 + service.py storage_path 既有）
- **测试：** ✅ 单元 335 过/1 败（`test_batch` 需 Redis broker，环境）；集成 45 过/5 败（PostgreSQL/LLM 环境依赖）；SSRF 防护 11 用例实测全过；E2E 未跑（需完整外部环境）
- **复盘结果：** 分阶段（P0→P1→P2→P2.5）逐项验收通过；删除 4 个半实现/假实现/有安全风险功能；单一入口收敛前端对接；URL 文档可分析可入库；多格式上传自动入图；修复 3 处自引入 ruff/GBK 编码问题
- **潜在风险：** 统一入口改动面大需持续回归；URL 抓取依赖外网可达；生产必需外部服务（PostgreSQL/Redis/MinIO/Neo4j/LLM API）本环境未全部实测；文档更新（docs/*.md）已同步

### 2026-07-28

#### 22. 全量 Code Review 修复（7 项）

- **时间：** 2026-07-28
- **发起人：** user（"先全部修复"）
- **依据：** 全量代码审查报告（功能断点 / 数据流断裂 / 空实现）
- **修改文件：**
  - `app/api/routes/chat.py:73-78` — 修复 `task_info.get('task_id')` → `task_id`（`create_task()` 返回 `str` 非 `dict`，complex_generation 路径必崩溃）
  - `app/orchestrator/nodes/save_session.py` — 移除对 `state["_runtime"]` 的依赖（该字段从未注入），改为通过 `connection_manager.get("postgres")` 自行创建 DB 会话，确保会话结果写入 PostgreSQL
  - `app/batch/scheduler.py:55-63` — `trigger_now()` 从空实现（仅返回 `{"success": True}`）改为通过 `celery_app.send_task()` 真正触发 Celery 任务
  - `app/llm_gateway/capabilities/image_encoder.py:113,127` — `_api_encode_image()` / `_api_encode_text()` 从 `raise NotImplementedError` 改为自动降级到 `_local_encode_*()` + `logger.warning`
  - `app/analysis_layer/nodes/lang_detector.py:50` — `except Exception: pass` → `except Exception as exc: logger.warning(...)`
  - `app/planning_layer/nodes/plan_self_check.py:41` — `except Exception:` → `except Exception as exc: logger.warning(...)`
- **Lint 验证：** ✅ `ruff check` All checks passed

- **时间：** 2026-07-28
- **发起人：** user（"全部改造"）
- **依据：** `docs/deep-review-fix-plan.md` Section 3（LangChain 节点内部重构）
- **修改内容：**
  - **Planning Layer (11/11)：** 全部节点从手动 `call_llm_async()` + `json.loads()` → `ChatPromptTemplate` + `GatewayChatModel` + `PydanticOutputParser`；新建 `planning_layer/output_models.py`（6 个 Pydantic 输出模型）
  - **Generation Layer (3/3)：** `code_scaffold_node` / `consistency_checker` / `revision_node` 同上改造
  - **Evaluation Layer (9/9)：** 全部节点从 `call_llm` + `parse_score` → `ChatPromptTemplate` + `PydanticOutputParser(ScoreResult)`；修复返回值从部分 dict → `{**state, ...}` 合并
  - **tools.py 清理：** 删除 `planning_layer/tools.py` 的 `call_llm_async`（11 节点已不再调用）；删除 `generation_layer/tools.py` 的 `call_llm_async`（3 节点已不再调用）；删除 `evaluation/tools.py` 的 `parse_score`（9 节点已用 PydanticOutputParser）；删除 `analysis_layer/tools.py` 的 `call_llm_async` + `extract_json_from_llm`（死代码）
- **新增文件：** 1 个（`planning_layer/output_models.py`）
- **修改文件：** 23 个节点 + 4 个 tools.py
- **Lint 验证：** ✅ `ruff check` All checks passed

#### 20. deep-review-fix-plan 未完成项补充 (Phase 2-5 收尾)

- **时间：** 2026-07-28
- **发起人：** user（"补充完整"）
- **依据：** `docs/deep-review-fix-plan.md` 完成度评估报告（总完成度约 70%）
- **修改内容：**
  - **意图路由接入（Phase 2.3/2.4）：** `build_orchestrator_graph()` 新增 `classify` 入口节点 → `route_by_intent` 条件路由；新建 `ChatNode` / `KnowledgeQANode` / `ClarifyNode` 三个节点；chat/knowledge_qa/clarification 路径全部在 LangGraph 图内运行
  - **SSE 移入节点（Phase 2.1）：** `ChatNode` + `KnowledgeQANode` 内嵌 SSE 副作用（通过 `_runtime.event_bus.publish()`），替代 TaskManager `astream` 循环中的硬编码 SSE
  - **TaskManager 适配（Phase 2.8）：** `_update_result()` 支持 `chat_response` 字段；简单对话/知识查询结果正确存储和推送
  - **chat.py 走 LangGraph（Phase 2.4）：** `POST /chat` 改为 `orchestrator.ainvoke()` 统一入口，不再手动 `if/elif` 调用 `gateway.complete()`
  - **GenerationAdapter export_formats（Phase 4.3）：** `OrchestratorState` 新增 `export_formats` 字段；`GenerationAdapter` 双向传递（输入→子图 / 子图结果→State）
  - **Session thread_id 绑定（Phase 3.3）：** `SessionRepository.create_session()` 自动生成 `thread_id`（uuid4）；`_to_session_out()` 映射 `thread_id` / `checkpoint_ts` / `current_node` / `interrupt_stage`
  - **死代码清理（Phase 5）：** 删除 3 个孤儿测试文件（`test_task_queue.py` / `test_task_executor.py` / `test_tool_registry.py`）；`ToolRegistry` 从 `__all__` 移除
- **新增文件：** 3 个（`orchestrator/nodes/chat_node.py` / `retrieve_node.py` / `clarify_node.py`）
- **修改文件：** 10 个（`main_graph.py` / `state.py` / `nodes/__init__.py` / `save_session.py` / `chat.py` / `task_manager.py` / `deps.py` / `generation_adapter.py` / `repository.py` / `agents/__init__.py`）
- **删除文件：** 3 个（孤儿测试文件）
- **Lint 验证：** ✅ `ruff check` All checks passed
- **潜在风险：** `chat.py` 的 `orchestrator.ainvoke()` 对 complex_generation 意图走 `task_manager.create_task()` 异步路径，避免了同步阻塞；新增节点依赖 `_runtime.event_bus` 注入，需确保 `RuntimeInjector` 在生命周期中正确初始化

#### 19. deep-review-fix-plan 全 Phase 实施

- **时间：** 2026-07-28
- **发起人：** user
- **依据：** `docs/deep-review-fix-plan.md`
- **修改内容：**
  - **Phase 1（Checkpoint 持久化）：** 新增 `langgraph-checkpoint-postgres` + `langchain-core` 依赖；`MemorySaver` → `PostgresSaver`（`build_and_compile` 支持注入 checkpointer）；新增 `OrchestratorConfig` / `OrchestratorRuntime`（Config/State/Runtime 三层分离）；`main.py` lifespan 中初始化 PostgresSaver
  - **Phase 2-3（LangGraph 全链路 + 记忆增强）：** 新建 `orchestrator/nodes/` 目录，新增 `SaveSessionNode` / `CompressMemoryNode` / `RetrieveMemoryNode` / `IntentClassifyNode`；新建 `orchestrator/runtime.py`（RuntimeInjector）；主图入口改为 `retrieve_memory → knowledge_retrieval → ... → compress_memory → save_session → END`
  - **Phase 4（数据流修复）：** `AnalysisResultDetail` 新增 `stakeholders` + `clarity_issues` 字段；`AnalysisResultAssemblerNode` 消费这两个字段（修复 Token 浪费）；`plan_assembler.py` 已正确将 `node_outputs` 放入 `metadata`
  - **Phase 5（死代码清理）：** 删除 `app/core/llm.py`（死代码）；删除 `app/core/task_executor.py`（含不存在的 `EvaluationOrchestrator` 引用）；删除 `app/core/task_queue.py`（零接入）；修复 `main.py` CORS 配置（`allow_credentials=False`）
  - **Phase 6（LangChain 适配器）：** 新建 `app/llm_gateway/langchain_adapter.py`（`GatewayChatModel` 包装 LLM Gateway 为 LangChain `BaseChatModel`）
  - **Phase 7（护栏扩展）：** 新建 `TimeoutGuardrail` / `EmptyResponseGuardrail` / `RetryDecisionGuardrail`；更新 `guardrails/__init__.py` 导出
  - **Phase 8（知识层接口）：** 新建 `app/knowledge_layer/interfaces.py`（6 个 Protocol 接口：DocumentReader / TextChunker / TextEmbedder / QueryRewriterInterface / ResultFuser / ResultReranker）
- **新增文件：** 13 个
- **删除文件：** 3 个（`core/llm.py` / `core/task_executor.py` / `core/task_queue.py`）
- **修改文件：** 12 个
- **潜在风险：** PostgresSaver 需要 PostgreSQL 运行和 `langgraph_checkpoints` 表自动创建；GatewayChatModel 的 `_messages_to_prompt` 可能丢失复杂消息结构（tool calls / multimodal）；新节点需在 `get_orchestrator()` 中正确注入 session_service / compressor / retriever

### 2026-07-27

#### 18. 全链路深挖 + 架构重构方案

- **时间：** 2026-07-27
- **发起人：** code-review 全链路深挖
- **产物：** `docs/deep-review-fix-plan.md`
- **审查范围：** 4 层 LangGraph 43 节点 + 18 API 路由模块 + 全部基础设施组件
- **发现问题：**
  - 🔴 5 个运行时严重问题（`get_retrieval_pipeline` 不存在、`EvaluationOrchestrator` 不存在、`ToolRegistry` 零使用、`PlanSelfCheck` 结果不路由、Celery 任务空壳）
  - 🟡 7 个数据流断裂（stakeholders/clarity_issues 无消费者、Planning 7 节点产出沉入 metadata 等）
  - 🟡 3 个架构缺陷（LangGraph 未全链路编排、无断点恢复、记忆组件零调用）
  - 12 个文件/模块使用了自定义流程编排（`asyncio.create_task`、`if/elif` 分支、手动 `try/except` 降级）代替 LangGraph 图节点
  - 43 个节点全部使用自定义 `call_llm_async()` + 手动 JSON 解析代替 LangChain 的 LCEL/Prompt/OutputParser
- **重构方案核心：**
  - LangGraph 全链路编排（SSE/会话/记忆/分类全部入图）
  - LangChain 接管节点内部（`ChatPromptTemplate` / `with_structured_output` / `PydanticOutputParser` / `bind_tools`）
  - LLM Gateway 包装为 `GatewayChatModel(BaseChatModel)`，保留成本追踪同时提供 LangChain 标准接口
  - PostgreSQL Checkpointer 替换 MemorySaver（崩溃可恢复）
  - Config / State / Runtime 三层分离
  - Session ↔ Thread 双向绑定（历史会话可续接）
- **架构原则（不变逻辑）：**
  - LLM Gateway / Guardrails / ContextCompressor / MemoryRetriever / SessionHistoryService / EventBus **现有逻辑全部保持不变**，仅解决接线问题
  - **错误处理进入护栏体系**：新增 `TimeoutGuardrail` / `EmptyResponseGuardrail` / `RetryDecisionGuardrail` 三个护栏插件，`GuardrailResult.metadata` 驱动 LangGraph 条件路由（retry/blocked/continue）
- **删除清单：** 3 个 `tools.py` 的重复 `call_llm_async`、`extract_json_from_llm`、`parse_score`、`app/core/llm.py`（死代码）、`ToolRegistry`、6 处手动 `try/except` 错误处理
- **Token 浪费统计：** 每次完整运行浪费约 6,000 tokens（25%）
- **综合评分：** ⚠️ CONDITIONAL PASS (78% 通过率)

---

### 2026-07-27

#### 17. Block E — SSE 流式推送（E12）

- **时间：** 2026-07-27
- **发起人：** 设计文档 `docs/block-E-enterprise.md` §11 E12
- **新增文件：**
  - `app/streaming/__init__.py` — SSE 模块入口
  - `app/streaming/event_bus.py` — EventBus 内存 Pub/Sub（asyncio.Queue）
  - `app/streaming/models.py` — SseEvent dataclass + EVENT_TYPES 常量
  - `app/api/schemas/streaming.py` — 流式请求体模型
  - `app/api/routes/stream_generate.py` — SSE 端点（任务事件流 + 流式生成 + 流式审核恢复）
  - `app/api/routes/stream_qna.py` — SSE 流式 Q&A 端点
  - `tests/unit/test_streaming.py` — 16 个单元测试
- **修改文件：**
  - `app/llm_gateway/providers/base.py` — 添加 `stream_complete()` 抽象方法
  - `app/llm_gateway/providers/openai.py` — 实现 `stream_complete()`（stream=True 逐 token yield）
  - `app/llm_gateway/providers/anthropic.py` — `stream_complete()` 预留实现
  - `app/llm_gateway/providers/cohere.py` — `stream_complete()` 预留实现
  - `app/llm_gateway/providers/custom.py` — 实现 `stream_complete()`（复用 OpenAI 兼容 API）
  - `app/llm_gateway/__init__.py` — 添加 `LLMGateway.stream_complete()` 门面方法
  - `app/task_manager.py` — 集成 EventBus（set_event_bus 注入 + _emit 事件发布）
  - `app/main.py` — 注册 SSE 路由 + lifespan 初始化 EventBus
  - `app/api/schemas/__init__.py` — 导出流式 Schema
  - `app/api/routes/__init__.py` — 导出流式路由
- **SSE 端点一览：**
  - `GET /api/v1/tasks/{task_id}/events` — 订阅任务事件流
  - `POST /api/v1/generate/stream` — 一键提交 + 全程 SSE 推送
  - `POST /api/v1/tasks/{task_id}/stream-review` — 审核 + 流式恢复
  - `POST /api/v1/qna/stream` — 流式 Q&A（检索 + LLM 流式回答）
- **测试结果：** 16/16 PASS，回归 334/334 PASS，ruff lint 全部通过
- **第二轮修复（code-review 后）：**
  - `generation.chunk`/`section` 事件：SectionWriterNode 接入 EventBus，使用 `gateway.stream_complete()` 流式调用 + 每 200 字符推送 chunk
  - `stream_complete()` Failover 链：for 循环重试 3 次，自动切换 Provider
  - `task.progress` 中间进度：TaskManager 改用 `astream` 替代 `ainvoke`，每步节点执行后读取 progress 并推送
  - 代码去重：提取 `_subscribe_task_events()` / `_sse_response()` 辅助函数，3 个端点复用
  - `TaskInfo` 新增 `stage` / `interrupt_stage` 字段，消除 `getattr` 兜底
  - `OpenAIProvider._complete_stream()` 移除未使用变量 `stream_params`
  - 生成层 `GenerationState` 新增 `task_id` 字段，`GenerationAdapter` 透传
- **潜在风险：** 无（所有 review 发现的问题已修复）

### 2026-07-27

#### 16. Block F — 生产级加固（12 项功能）

- **时间：** 2026-07-27
- **发起人：** 设计文档 `docs/block-F-production-hardening.md`
- **新增文件：** 40+ 文件
  - `app/core/circuit_breaker.py` — 装饰器式熔断器（CLOSED→OPEN→HALF_OPEN 状态机）
  - `app/llm_gateway/output_parser.py` — Pydantic 输出解析器（response_format→Prompt 降级）
  - `app/llm_gateway/prompt_builder.py` — 统一 Prompt 构建器
  - `app/knowledge_layer/ingestion/claims_extractor.py` — Claims 决策断言提取
  - `app/llm_gateway/failover.py` — Provider Failover 链管理
  - `app/llm_gateway/guardrails/` — 可插拔护栏（注入检测/内容安全/PII/输出校验）
  - `app/core/task_queue.py` — 优先级任务队列（heapq + 取消 + 持久化）
  - `app/core/task_executor.py` — 任务执行器注册器（Generate/Reindex/Evaluate/WebSync）
  - `app/auth/prompts/` — 多租户 Prompt 隔离（三级回退 + Jinja2 渲染）
  - `app/session_history/compressor.py` — 上下文压缩器（summarize/rolling/truncate）
  - `app/session_history/memory_retriever.py` — 多策略记忆检索（recency/relevance/importance/hybrid）
  - `app/session_history/summarizer.py` — ⬆️ 重写为 LLM 驱动
  - `app/agents/` — Tool Registry 工具系统（8 个具体工具）
  - `app/orchestrator/intent_classifier.py` — 意图分类器（规则+LLM 双保险）
  - `app/core/prompt_registry/` — Prompt 版本管理（版本化/回滚/diff/A-B 测试）
  - `app/observability/replay/` — Agent 行为回放（录制/回放/分析）
  - `contracts/models.py` — ⬆️ 新增 8 个模型（Task/MemoryItem/DecisionRecord 等）
- **测试：** `tests/unit/block_f/` — 46 个单元测试全部通过
- **Lint：** ruff check 全部通过
- **潜在风险：** FailoverManager 和 GuardrailManager 集成到 LLMGateway 需在后续迭代完成

### 2026-07-26

#### 15. E12 — SSE 流式推送设计

- **时间：** 2026-07-26
- **发起人：** 用户需求
- **新增于：** `docs/block-E-enterprise.md` §11
- **设计内容：**
  - **EventBus** — 基于 `asyncio.Queue` 的内存 Pub/Sub，按 channel 发布/订阅
  - **SSE 端点** — 4 个：
    - `GET /api/v1/tasks/{task_id}/events` — 任务事件流
    - `POST /api/v1/generate/stream` — 一键提交 + 全程 SSE
    - `POST /api/v1/qna/stream` — 流式 Q&A
    - `POST /api/v1/tasks/{task_id}/stream-review` — 审核 + 流式恢复
  - **LLM Gateway** — `stream_complete()` 流式调用，Provider 层 yield token chunks
  - **Generation Layer** — SectionWriter 逐 chunk 推送文档片段
  - **TaskManager** — 执行过程 10+ 埋点 emit 事件
  - **流式 Q&A** — 检索 → LLM 流式回答 → done
  - **14 种 SSE 事件类型** + 重连恢复 + 心跳保活
  - 详见 `docs/block-E-enterprise.md` §11

### 2026-07-24

#### 14. 多轮自省修复：Gateway 加固 / 线程安全 / 配置补全 / Alembic 修正 / Auth 安全

- **时间：** 2026-07-24 19:30:00
- **发起人：** `grill-me` 多轮自省触发
- **修改文件：**
  - `app/llm_gateway/__init__.py` — **修复** embed/rerank 加入速率限制；限流路径返回 model 名；`**kwargs` 类型 `dict`→`Any`
  - `app/llm_gateway/pricing.py` — **新增** 统一定价常量模块，消除定价表重复定义
  - `app/llm_gateway/cost_tracker.py` — **修复** 定价引用切到统一模块；加 `Lock` 线程安全
  - `app/llm_gateway/rate_limiter.py` — **修复** 加 `Lock` 线程安全
  - `app/llm_gateway/cache.py` — **修复** 加 `Lock` 线程安全
  - `app/llm_gateway/providers/openai.py` — **修复** 定价引用切到统一模块
  - `app/llm_gateway/providers/base.py` — **修复** `BaseProvider` 改用 `ABC` + `@abstractmethod`
  - `app/llm_gateway/providers/anthropic.py` — **修复** 补充 `embed()`/`rerank()` stub 方法
  - `app/llm_gateway/router.py` — **修复** 标记为已废弃（功能已合并到 `ModelConfigManager`）
  - `app/analysis_layer/tools.py` — **修复** `call_llm_async()` 添加异常日志，不再静默吞错误
  - `app/planning_layer/tools.py` — **修复** 同上
  - `app/generation_layer/tools.py` — **修复** 同上；`task_type` 改为 `"generation"`
  - `app/evaluation/tools.py` — **修复** 同上；`task_type` 改为 `"evaluation_scoring"`
  - `app/core/config.py` — **修复** 新增 `MODEL_ROUTING__GENERATION__*`；移除死配置 `analysis_constraint`
  - `.env.example` — **修复** 新增 Block E 配置（OTEL/Budget/RateLimit）+ generation 路由规则
  - `alembic/versions/a1b2c3d4e5f6_add_block_e_tables.py` — **修复** 改为仅修复 tags 类型不一致，不再重复创建表
  - `alembic/env.py` — **修复** 导入所有模型子类以支持 autogenerate
  - `app/orchestrator/iteration.py` — **修复** 移除 `report is None` 分支中的重复 `iteration_count` 递增
  - `app/auth/middleware.py` — **修复** `WorkspaceContextMiddleware` 增加注释说明 JWT Token 不可被请求头覆盖
  - `app/api/deps.py` — **修复** `get_masking_engine()` 改为单例缓存
  - `app/api/schemas/__init__.py` — **修复** 补全 5 个缺失的 schema 模块导出
  - `app/api/routes/__init__.py` — **修复** 新增 `__all__`
  - `app/llm_gateway/__init__.py` — **修复** 移除 `ModelRouter` 参数和导入
  - `app/core/llm.py` — **修复** 添加 `DeprecationWarning` 和迁移指引
  - `app/llm_gateway/capabilities/image_encoder.py` — **修复** mode property 补充 docstring
- **修改内容：** 多轮 `grill-me` 自省触发的批量修复：
  - **Gateway 加固**：`embed()`/`rerank()` 加入速率限制；限流路径返回正确 model 名；`**kwargs` 类型修正
  - **线程安全**：`CostTracker` / `RateLimiter` / `SemanticCache` 三个内存存储加 `Lock`
  - **定价统一**：新增 `app/llm_gateway/pricing.py`，消除 `CostTracker` 和 `OpenAIProvider` 之间的定价表重复
  - **异常可见性**：4 个 Agent Layer 的 `call_llm_async()` 静默 `except` 改为记录 warning 日志
  - **配置补全**：`.env.example` 补全 Block E 的 OTEL/Budget/RateLimit 共 8 项配置；新增 `generation` 路由规则；移除 `analysis_constraint` 死配置
  - **Alembic 修正**：迁移 2 改为仅修复 `tags` 类型不一致（`ARRAY(String)→JSONB`），不再重复创建已存在的表；`env.py` 导入所有模型子类以支持 autogenerate
  - **Orchestrator 修正**：`IterationDecider` `report is None` 分支移除重复的 `iteration_count` 递增
  - **Auth 安全**：`WorkspaceContextMiddleware` 增加注释说明 JWT Token 中的 `ws_id` 不可被请求头覆盖
  - **代码清理**：`ModelRouter` 标记废弃；`app/core/llm.py` 添加 DeprecationWarning；`schemas/__init__.py` 补全导出
- **复盘结果：**
  - 193/193 单元测试全部通过 ✅
  - 全部 schema 导入正常 ✅
  - 路由系统真正生效（evaluation→gpt-4o-mini 等）✅
  - 零新增外部依赖 ✅
- **潜在风险：** Alembic 迁移 2 的 `ALTER COLUMN tags TYPE JSONB` 在已有大数据量时可能较慢；内存存储的线程安全锁在极高并发下仍是瓶颈（后续可迁到 Redis）

#### 13. Gateway 统一重构：所有模型调用接入网关 + Capabilities 层 + 本地模型兜底

- **时间：** 2026-07-24 18:55:00
- **发起人：** Copilot 自省报告触发
- **修改文件：**
  - `app/llm_gateway/capabilities/` — **新增 4 个文件**（`__init__.py` / `embedding.py` / `reranking.py` / `image_encoder.py`）
  - `app/llm_gateway/__init__.py` — **增强** 注入 Capabilities 层，新增 `encode_image()` / `encode_text()` 方法；`embed()` / `rerank()` 改为通过 Capability 执行
  - `app/analysis_layer/tools.py` — `call_llm_async()` 从 `app.core.llm` 切到 `gateway.complete()`
  - `app/planning_layer/tools.py` — 同上
  - `app/generation_layer/tools.py` — 同上
  - `app/evaluation/tools.py` — `call_llm()` 从 `app.core.llm` 切到 `gateway.complete()`
  - `app/knowledge_layer/ingestion/entity_extractor.py` — `llm_complete()` → `gateway.complete()`
  - `app/knowledge_layer/retrieval/rewriter.py` — 同上
  - `app/knowledge_layer/retrieval/global_search.py` — 同上
  - `app/knowledge_layer/retrieval/reflection.py` — 同上
  - `app/knowledge_layer/ingestion/entity_embedder.py` — **重写** 新增 `embed_texts()` 方法；`embed_text()` / `embed_entity()` 改为 async，通过 `gateway.embed()` API 优先 → 本地 SentenceTransformer 兜底
  - `app/knowledge_layer/pipeline.py` — `entity_embedder.embed_entity()` / `embed_text()` 调用改为 `await`
  - `app/web_indexing/search_fallback.py` — `EntityEmbedder.embed_text()` 调用改为 `await`
  - `app/core/config.py` — **新增** `EMBEDDING_MODE` / `RERANK_MODE` / `IMAGE_ENCODE_MODE` / `CLIP_MODEL_NAME` 配置项
  - `.env.example` — **新增** Capability 模式配置和 CLIP 配置
  - `tests/integration/test_kg_build.py` — Mock 适配 async 接口
- **修改内容：** 将项目中所有模型调用统一接入 LLM Gateway：
  - **新增 Capabilities 层**（`app/llm_gateway/capabilities/`）：三个 Capability 实现"API 优先，本地模型兜底"策略
    - `UnifiedEmbedding`：API (OpenAI `text-embedding-3-small`) → 本地 (SentenceTransformer `BAAI/bge-large-zh-v1.5`)
    - `UnifiedReranking`：API (Cohere `rerank-english-v3.0`) → 本地 (BGE `bge-reranker-v2-m3`)
    - `UnifiedImageEncoder`：API (预留) → 本地 (CLIP `openai/clip-vit-base-patch32`)
  - **LLM 调用统一**：4 个 Agent Layer 的 `call_llm_async()`/`call_llm()` + 4 个 Knowledge Layer 文件，全部从 `app.core.llm.llm_complete()` 切到 `gateway.complete()`
  - **Embedding 统一**：`EntityEmbedder` 改为 async，优先调用 `gateway.embed()`，API 失败时自动降级到本地模型
  - **配置扩展**：新增 `EMBEDDING_MODE` / `RERANK_MODE` / `IMAGE_ENCODE_MODE`（auto/api/local 三模式），遵循三级优先级（环境变量 → .env → 代码默认值）
  - **架构解耦**：`app.core.llm`（旧模块）成为死代码，零耦合遗留
- **复盘结果：**
  - 30+ 处 LLM 调用全部接入 Gateway ✅
  - 3 个本地模型（SentenceTransformer / BGE / CLIP）统一为 API→本地兜底 ✅
  - 4 个 Agent Layer + 知识层测试全部通过 ✅
  - ruff 0 errors ✅
  - 零修改 contracts/ ✅
- **潜在风险：** EntityEmbedder 改为 async 后，同步调用方需加 `await`；旧 `app.core.llm` 模块可择机清理；CLIP 图片编码当前无 API 替代，仅支持 local 模式

#### 12. 块 E 回补：E7 KG 集成 / E11 LLM 关键词+结果索引 / E5 Webhook 接入管线 / Celery 容器化 / 集成测试

- **时间：** 2026-07-24 17:10:00
- **发起人：** Copilot 自省报告触发
- **修改文件：**
  - `app/knowledge_layer/pipeline.py` — **增强** KnowledgeGraphBuilder 新增 `build_from_text()` 方法，支持从文本（无文件路径）构建实体索引
  - `app/knowledge_layer/pipeline.py` — **增强** RetrievalPipeline.retrieve() 结果不足时自动触发 SearchFallback 回退搜索引擎
  - `app/web_indexing/search_fallback.py` — **重写** SearchFallback 新增 LLM 关键词生成（`generate_search_keywords`）、`search_and_index()` 实时索引到 PGVector
  - `app/orchestrator/main_graph.py` — **增强** FinalAssemblyNode 任务完成后自动触发 Webhook 通知
  - `app/api/routes/web_indexing.py` — **增强** fetch/crawl 端点支持 `index_to_kg` 参数，自动将抓取内容写入知识图谱；search-fallback 端点传入 LLM Gateway + 结果索引
  - `docker-compose.yml` — **新增** `celery-worker` 和 `celery-beat` 容器
  - `tests/integration/test_web_crawling.py` — **新增** 6 个集成测试（WebLoader/WebCrawler/WebSync）
  - `tests/integration/test_search_fallback.py` — **新增** 8 个集成测试（SearchFallback LLM 关键词/HTML 解析/search_and_index）
  - `tests/integration/test_integrations.py` — **新增** 10 个集成测试（Webhook 发送/IntegrationHub/Orchestrator 联动）
  - `tests/integration/test_kg_build.py` — **新增** 2 个集成测试（build_from_text / 空文本）
  - `tests/unit/test_web_indexing.py` — **新增** 4 个单元测试（LLM 关键词生成/search_and_index 向量存储索引）
- **修改内容：** 回补自省报告发现的 3 个严重功能缺口 + 2 个中等集成问题：
  - **E7 KG 集成（严重）**：`WebLoader.fetch()` 抓取的网页内容通过 `KnowledgeGraphBuilder.build_from_text()` 自动写入 Neo4j + PGVector，不再仅是返回文本
  - **E11 LLM 关键词生成（严重）**：`SearchFallback.search()` 先调用 LLM Gateway 生成搜索关键词再查询 DuckDuckGo，LLM 不可用时优雅降级
  - **E11 结果实时索引（严重）**：`SearchFallback.search_and_index()` 将搜索结果通过 EntityEmbedder 编码后写入 `text_unit_embeddings` 表
  - **E5 Webhook 接入管线（中等）**：`FinalAssemblyNode.run()` 完成后自动调用 `IntegrationHub.notify()` 发送 Webhook 通知，失败不阻塞主流程
  - **E11 自动回退（中等）**：`RetrievalPipeline.retrieve()` 在结果 < 3 条时自动触发 SearchFallback，结果转为 ScoredDoc 追加
  - **Celery 容器化（中等）**：docker-compose.yml 新增 celery-worker（concurrency=4）和 celery-beat 容器
  - **集成测试全覆盖**：3 个新集成测试文件（24 个测试用例）+ 补充单元测试（4 个）
- **复盘结果：**
  - 3 个严重功能缺口全部回补 ✅
  - 2 个中等集成问题全部修复 ✅
  - 新增 24 个集成测试 + 4 个单元测试 ✅
  - 零修改 contracts/ ✅
  - 块 A/B/C/D 核心代码零修改 ✅
- **潜在风险：** LLM 关键词生成增加搜索延迟（~500ms）；DuckDuckGo HTML 解析依赖页面结构，可能因搜索引擎改版而失效；Celery Worker 需 `docker compose up -d` 后单独启动

#### 11. 块 E Session 5：CLIP 多模态（E8）+ 协作文档（E9）+ 批量任务（E10）— 块 E 收官

- **时间：** 2026-07-24 16:40:00
- **发起人：** user
- **修改文件：**
  - `app/multimodal/` — **新增 5 个文件**（CLIP 编码器/ImageChunk 存储/多模态检索/图片预览）
  - `app/collaboration/` — **新增 6 个文件**（评论/建议/变更历史/服务/模型）
  - `app/batch/` — **新增 3 个文件**（调度器/批量任务）
  - `app/api/routes/multimodal.py` — **新增** 4 个端点（索引/以图搜图/文搜图/混合检索）
  - `app/api/routes/collaboration.py` — **新增** 8 个端点（评论 CRUD/建议审批/变更历史）
  - `app/api/routes/batch.py` — **新增** 5 个端点（重索引/重新生成/任务状态/定时触发）
  - `app/api/schemas/multimodal.py` / `collaboration.py` / `batch.py` — **新增** 3 个 schema 文件
  - `app/main.py` — 注册 multimodal / collaboration / batch 路由
  - `tests/unit/test_multimodal.py` — **新增** 7 个测试
  - `tests/unit/test_collaboration.py` — **新增** 9 个测试
  - `tests/unit/test_batch.py` — **新增** 8 个测试
- **修改内容：** 完成块 E 最后 3 个子功能：
  - **E8 CLIP 多模态**：ClipEncoder（transformers CLIP 双塔编码，真实模型自动加载，无模型时返回模拟向量）、ImageChunkStore（双向量 visual_emb + text_emb 内存存储）、MultimodalSearchService（以图搜图/文搜图/RRF 融合混合检索）、ImagePreviewGenerator（Pillow 缩略图生成）
  - **E9 协作文档**：CommentService（行内评论+回复+解决）、SuggestionService（建议创建/审批/拒绝）、ChangeLogService（变更历史自动记录）、CollaborationService（统一组合）
  - **E10 批量任务**：BatchTaskService（批量重索引/重新生成/进度跟踪）、BatchScheduler（Celery Beat 配置：知识图谱24h/会话清理1h/Web同步2h）
- **复盘结果：**
  - 24/24 新增测试全部通过 ✅
  - ruff 新增文件 0 errors ✅
  - 零修改块 A/B/C/D 代码 ✅
  - **块 E 全部 11 项子功能（E1-E11）实现完成** 🎉
- **潜在风险：** CLIP 模型首次调用需从 HuggingFace 下载（~670MB），后续缓存后加快；Celery Worker 需要单独启动进程；协作文档当前使用内存存储，生产环境需迁移到 DB

#### 10. 块 E Session 3：文档管理（E4）+ CSV 双通路索引（E6）+ API 路由

- **时间：** 2026-07-24 16:20:00
- **发起人：** user
- **修改文件：**
  - `app/document_management/` — **新增 9 个文件**（`__init__`/`models`/`repository`/`service`/`storage`/`deduplication`/`preview`/`search`/`csv_loader`）
  - `app/api/routes/documents.py` — **新增** 8 个 RESTful 端点（含 CSV 导入）
  - `app/api/schemas/document.py` — **新增** 文档 API 请求/响应体
  - `app/api/schemas/__init__.py` — 导出文档 schemas
  - `app/main.py` — 注册 `documents_routes`
  - `tests/unit/test_document_management.py` — **新增** 18 个单元测试
- **修改内容：** 完整实现 E4 文档管理 + E6 CSV 双通路索引：
  - **E4 文档管理**：DocumentRepository（CRUD + 哈希查重 + 软删除 + 分页 + 统计看板）；DocumentStorage（MinIO 对象存储，`prd-docs/{ws}/{yy}/{mm}/{hash}.ext`）；DocumentDeduplicator（SHA-256 去重）；DocumentPreviewGenerator（Markdown/CSV/文本/PDF/图片预览）；DocumentSearchService（PostgreSQL FTS 全文搜索文件名+描述）
  - **E6 CSV 双通路索引**：CsvDualPathIndexer — 行级 TextUnit（每行→自然语言句子）、列级分析（类型推断 integer/float/date/enum/string）、外键自动检测（`_id`/`_key` 后缀启发）
  - **API 路由**：8 个端点 — POST upload、GET list/search、GET stats、GET by_id、DELETE、GET preview、POST reindex、POST csv-import
- **复盘结果：**
  - 180/180 测试全部通过 ✅（18 个新增 + 162 个回归）
  - ruff 新增文件 0 errors ✅
  - 零修改块 A/B/C/D 代码 ✅
- **潜在风险：** MinIO 存储依赖 `app/core/connections` 中的 MinIO 连接器（当前 lazy init，需在 health 端手动触发激活）；CSV 预览截取前 21 行，大文件预览可能不完整

#### 9. 块 E Session 2：会话历史管理（E3）全模块 + API 路由

- **时间：** 2026-07-24 16:10:00
- **发起人：** user
- **修改文件：**
  - `app/session_history/` — **新增 8 个文件**（`__init__`/`models`/`repository`/`service`/`search`/`exporter`/`summarizer`/`cleanup`）
  - `app/api/routes/sessions.py` — **新增** 9 个 RESTful 端点
  - `app/api/schemas/session.py` — **新增** 会话 API 请求/响应体
  - `app/api/schemas/__init__.py` — 导出会话 schemas
  - `app/main.py` — 注册 `sessions_routes`
  - `tests/unit/test_session_history.py` — **新增** 15 个单元测试
- **修改内容：** 完整实现 E3 会话历史管理：
  - **Repository 层**：SessionRepository（CRUD + 软删除 + 分页 + 老化清理），ORM ↔ Pydantic 转换
  - **Service 层**：SessionHistoryService（统一组合 Repository/Search/Export/Summarizer/Cleanup）
  - **搜索**：SessionSearchService（PostgreSQL FTS `to_tsvector`/`plainto_tsquery` 全文搜索消息，`ilike` 标题搜索）
  - **导出**：SessionExporter（Markdown 带角色标签 + JSON 结构化导出）
  - **摘要**：SessionSummarizer（基于首条消息生成标题，基于消息内容生成摘要）
  - **清理**：SessionCleanupPolicy（Free 30天 / Pro 180天 / Enterprise 不限）
  - **API 路由**：9 个端点 — POST/GET/PUT/DELETE 会话、POST/GET 消息、搜索消息、导出、老化清理
- **复盘结果：**
  - 162/162 测试通过 ✅（15 个新增 + 147 个回归）
  - ruff 新增文件 0 errors ✅
  - 零修改块 A/B/C/D 代码 ✅
- **潜在风险：** FTS 搜索需 PostgreSQL 原生支持（SQLite 测试中会跳过）

#### 8. 块 E Session 1：基础设施增强 + LLM Gateway 增强（预算/限流/观测性）

- **时间：** 2026-07-24 15:45:00
- **发起人：** user
- **修改文件：**
  - `docker-compose.yml` — 新增 Jaeger + Prometheus 容器
  - `prometheus.yml` — 新增 Prometheus 抓取配置
  - `requirements.txt` — 新增 opentelemetry-api/sdk/exporter-otlp + prometheus-client
  - `app/models/block_e.py` — **新增** 块 E 全部 5 个 ORM 模型（LLMCallLog/BudgetConfig/Session/SessionMessage/UploadedDocument）
  - `app/models/__init__.py` — 导出新模型
  - `alembic/versions/938e6d4dcfd6_init_all_tables.py` — 重写：从空迁移改为完整创建 10 张表
  - `app/core/config.py` — 新增 Block E 配置（OTEL/Prometheus/Budget/RateLimit 默认值）
  - `app/llm_gateway/budget_controller.py` — **新增** BudgetController（月预算检查/告警/自动降级）
  - `app/llm_gateway/rate_limiter.py` — **新增** RateLimiter（滑动窗口 RPM+TPM 流控）
  - `app/llm_gateway/__init__.py` — **升级** LLMGateway.complete() 集成预算检查+速率限制+OpenTelemetry 追踪
  - `app/observability/__init__.py` — **新增** 观测性模块
  - `app/observability/tracing.py` — **新增** OpenTelemetry 追踪（TracingMiddleware + wrap_node/wrap_async_node）
  - `app/observability/metrics.py` — **新增** Prometheus 指标（LLM 调用/成本/延迟/Token/任务/会话/文档）
  - `app/observability/alerts.yml` — **新增** 4 条告警规则（高成本/高质量下降/高延迟/高失败率）
  - `app/main.py` — 注册 Prometheus `/api/v1/metrics` 端点，初始化追踪
  - `tests/unit/test_budget_controller.py` — **新增** 6 个测试
  - `tests/unit/test_rate_limiter.py` — **新增** 5 个测试
  - `tests/unit/test_observability.py` — **新增** 4 个测试
- **修改内容：** 块 E Session 1 基础底座搭建：
  - **基础设施**：docker-compose 添加 Jaeger（16686 UI + 4317 OTLP）+ Prometheus（9090）；新增 Prometheus 抓取配置
  - **数据模型**：LLMCallLog（每次 LLM 调用记录）、BudgetConfig（工作空间月预算配置）、Session（会话）、SessionMessage（会话消息，CASCADE 删除）、UploadedDocument（已上传文档）
  - **Alembic**：从空迁移重写为完整 10 张表（含块 A 的 5 张用户表 + 块 E 的 5 张企业表），含索引和约束
  - **LLM Gateway 增强**：BudgetController（月预算检查→超 90% 告警→超 100% 自动降级到低成本模型）、RateLimiter（滑动窗口 RPM+TPM 双维度限制）、LLMGateway.complete() 集成 9 步链路（限流→路由→预算→缓存→追踪→调用→缓存→成本→预算）
  - **观测性**：OpenTelemetry Tracer（OTLP gRPC 导出到 Jaeger）、TracingMiddleware（LangGraph Node 自动包装 Span）、Prometheus 指标（LLM 调用/成本/延迟/Token/任务/会话/文档）、4 条告警规则
- **复盘结果：**
  - 116/116 单元测试全部通过 ✅（含 15 个新增 + 101 个回归）
  - ruff 新增文件 0 errors ✅
  - 新增 5 个核心模块，零修改块 A/B/C/D 代码 ✅
- **潜在风险：** Alembic 迁移会删除已有数据（首次从空迁移改为完整迁移）；Jaeger/Prometheus 需 `docker compose up -d` 启动；`ARRAY`/`JSONB` 类型已替换为通用 `JSON` 以保证 SQLite 兼容

#### 7. 块 D 全链路串联 + API：Orchestrator + Adapter + 异步任务

- **时间：** 2026-07-24 13:10:00
- **发起人：** user
- **修改文件：**
  - `app/orchestrator/` — 新增 10 个文件（__init__/state/main_graph/routing/human_review/iteration + adapters/__init__ + 4 个 Adapter）
  - `app/task_manager.py` — 新增（in-memory 异步任务管理器）
  - `app/api/routes/generate.py` — 新增（POST /generate + GET /tasks/{id}）
  - `app/api/routes/review.py` — 新增（GET /review/pending + POST /review/{id}/{stage}）
  - `app/api/routes/evaluate.py` — 新增（POST /evaluate）
  - `app/api/deps.py` — 新增 get_orchestrator 懒加载依赖
  - `app/main.py` — 注册 3 个新路由
  - `tests/unit/test_orchestrator.py` — 新增（16 个单元测试）
  - `tests/integration/test_pipeline.py` — 新增（4 个集成测试）
  - `tests/e2e/test_full_flow.py` — 新增（端到端测试，需 RUN_E2E_TESTS=1）
- **修改内容：** 构建 Block D 全链路串联：
  - **OrchestratorState**（TypedDict + TenantContext + make_initial_state）：串联 4 层全局状态
  - **4 个 Adapter**（Analysis/Planning/Generation/Evaluation）：OrchestratorState ↔ LayerState 无损转换
  - **KnowledgeRetrievalNode**：调用块 B RetrievalPipeline，失败时优雅降级
  - **HumanReviewNode**：使用 LangGraph interrupt 机制暂停等待人工反馈
  - **IterationDecider**：评分≥85 接受 / ≥70 按维度回退 / <70 迭代或人工介入
  - **FinalAssemblyNode**：汇总输出
  - **TaskManager**：asyncio.create_task + in-memory dict 管理任务生命周期
- **复盘结果：**
  - 16/16 单元测试通过 ✅
  - 4/4 集成测试通过 ✅（Mock LLM + Mock Pipeline）
  - ruff 0 errors, ruff format 已对齐 ✅
  - 块 A/B/C 零修改 ✅（遵守铁律）
- **潜在风险：** 无

#### 6. 块 C 核心 Agent 流水线：4 层 LangGraph 实现

- **时间：** 2026-07-24 11:40:00
- **发起人：** user
- **修改文件：**
  - `contracts/interfaces.py` — 新增 Block C 增强模型（RequirementDetail/ConstraintDetail/AnalysisResultDetail/PatternEval/PlanningResultDetail/SectionOutline/GenerationResultDetail/EvaluationReportDetail 等）
  - `app/analysis_layer/` — 新增 13 个文件（__init__/models/tools/agent_graph + 9 个 nodes）
  - `app/planning_layer/` — 新增 16 个文件（__init__/models/tools/agent_graph + 13 个 nodes）
  - `app/generation_layer/` — 新增 15 个文件（__init__/models/tools/agent_graph + 8 个 nodes + templates 引擎）
  - `app/evaluation/` — 新增 14 个文件（__init__/models/tools/scoring/score_calibrator/agent_graph + 9 个 nodes）
  - `tests/unit/` — 新增 6 个测试文件（test_analysis_nodes/test_planning_nodes/test_generation_nodes/test_evaluation_nodes/test_template_engine/test_format_exporter）
  - `tests/integration/` — 新增 4 个测试文件（test_analysis_pipeline/test_planning_pipeline/test_generation_pipeline/test_evaluation_pipeline）
- **修改内容：** 构建 Block C 的 4 个 Agent Layer，每个 Layer 为 LangGraph StateGraph：
  - **C1 Analysis Layer**（11 nodes）：Markdown 解析 → 语言检测 → 需求提取 → 约束提取 → 依赖分析 → 领域分类 → 质量评分 → 工作量估算 → 干系人分析 → 清晰度检查 → 组装
  - **C2 Planning Layer**（14 nodes）：知识检索（块 B）→ 架构推荐 → 模式确认 → 技术栈选型 → 组件分解 → 成本估算 → 时间线 → 技能缺口 → 风险量化 → 数据架构 → API 规划 → 部署方案 → 自检 → 组装
  - **C3 Generation Layer**（8 nodes + 模板系统）：大纲生成 → 章节撰写 → Mermaid 图表 → 代码框架 → 一致性检查 → 修订 → 格式组装 → 多格式导出（占位）
  - **C4 Evaluation Layer**（10 nodes + 评分校准）：PRD 覆盖率 → 一致性 → 可行性 → 架构质量 → 安全合规 → 成本 → 可实施性 → 技术先进性 → 法律合规 → 评分
- **复盘结果：**
  - 81/81 单元测试全部通过 ✅
  - C1/C2/C3 集成测试通过 ✅（C4 需 API Key 环境）
  - 4 个 CompiledStateGraph 成功编译 ✅
  - LLM 调用失败时优雅降级（返回空结果）✅
  - ruff 0 errors ✅
- **潜在风险：** 无

#### 5. 块 B 精简重构：去掉过度设计，新增检索反思

- **时间：** 2026-07-24
- **发起人：** user
- **修改文件：**
  - `docs/block-B-knowledge-layer.md` — 全文更新（功能列表 15→11 项，链路重写，测试更新）
  - `app/knowledge_layer/pipeline.py` — KnowledgeGraphBuilder 从 13 步精简为 7 步；RetrievalPipeline 加入反思循环
  - `app/knowledge_layer/models.py` — BuildStats 去掉 relations/claims/version_id 等废弃字段
  - `app/knowledge_layer/ingestion/entity_resolver.py` — 四级消歧→两级（精确+别名）
  - `app/knowledge_layer/ingestion/entity_embedder.py` — 四源融合→双源（名称+描述）
  - `app/knowledge_layer/vector_store.py` — 去掉 claim_embeddings 建表和 upsert_claim_embedding
  - `app/knowledge_layer/graph_store.py` — 去掉 upsert_relation/upsert_text_unit/upsert_claim 等方法
  - `app/knowledge_layer/retrieval/local_search.py` — 适配 get_neighbors 新签名
  - `app/knowledge_layer/retrieval/reflection.py` — **新增** ReflectionJudge 检索反思裁判
  - `app/knowledge_layer/__init__.py` / `ingestion/__init__.py` / `retrieval/__init__.py` — 更新导入
  - `tests/integration/test_kg_build.py` — 适配新的 BuildStats 和 Builder 接口
  - `tests/integration/test_local_search_integration.py` — 适配 get_neighbors 新签名
  - `tests/unit/test_local_search.py` — 适配 get_neighbors 新签名
  - `tests/integration/test_auth_flow.py` — 修复：测试前调用 init_connections + startup
  - `tests/test_lint.py` — 修复：Python 3.14 兼容（ast.Str → ast.Constant，open 加 encoding）
  - **删除** 6 个文件：`relation_extractor.py`、`claims_extractor.py`、`knowledge_aging.py`、`kg_versioning.py`、`text_unit_builder.py`、`index_builder.py`
- **修改内容：** 对块 B 知识层做针对性精简：
  - **去掉**：关系提取 / Claims 提取 / TextUnit 构建 / 版本控制 / 知识老化 / LlamaIndex 索引（均为过度设计，无外部依赖方）
  - **简化**：实体消歧从四级（精确+别名+语义+人工）精简为两级（精确+别名）；实体 Embedding 从四源（名称+描述+TextUnit+Claims）精简为双源（名称+描述）；Global Search 去掉社区检测，改为按实体类型分组
  - **新增**：`ReflectionJudge` 检索反思裁判——每次检索后 LLM 判断结果质量，不满足时自动修正查询并重新检索（最多 2 轮），显著提升口述需求的命中率
  - **保留**：实体提取（口述→技术术语桥接的核心）、Neo4j 存储、PGVector 存储、检索管线全套（意图路由/重写/丰富/Local Search/Global Search/RRF 融合/重排/压缩）
- **复盘结果：**
  - 87/87 测试通过 ✅（含所有块 A 回归 + 依赖 Docker 容器的集成测试）
  - ruff 0 errors ✅
  - all .py 语法检查通过 ✅
  - Neo4j ✅ / PostgreSQL ✅ / Redis ✅ / MinIO ✅ 全部可连接
- **潜在风险：** 无

#### 4. 批量部署 skills 同步到 lania-zip 全部 14 个项目

- **时间：** 2026-07-24 13:30:00
- **发起人：** user
- **修改文件：**
  - `lania-shared-skills\setup-all-projects.ps1` — 新增批量安装脚本
  - 13 个项目（除 prd2tsd-agents 外）安装了 `.githooks/` + `sync-skills.ps1`
- **修改内容：** 通过 `setup-all-projects.ps1` 一键为所有项目配置：.githooks（pre-commit / post-commit / post-checkout）、sync-skills.ps1、git config core.hooksPath、git update-index --skip-worktree
- **复盘结果：** 全部 14 个项目统一完成配置。修改共享目录后，任一项目执行 git commit 自动同步 → Git 感知改动 → 提交后恢复 junction 实时同步
- **潜在风险：** setup-all-projects.ps1 仅在新增项目时需要重新执行

#### 3. 自动同步方案：junction + Git hooks 协同

- **时间：** 2026-07-24 13:00:00
- **发起人：** user
- **修改文件：**
  - `.github/skills/ai-coding-rules` — 替换为 Junction → `lania-shared-skills`（实时同步）
  - `.github/skills/debug-tools` — 替换为 Junction → `lania-shared-skills`（实时同步）
  - `.githooks/pre-commit` — 重写，提交前：拆 junction → 复制真实文件 → clear skip-worktree → git add
  - `.githooks/post-commit` — 新增，提交后：删真实文件 → 重建 junction → set skip-worktree
  - `.githooks/post-checkout` — 更新，检出后检测异常状态并恢复 junction
  - `sync-skills.ps1` — 重写，支持三种模式：默认/ToReal/ToJunction
- **修改内容：** 最终方案：开发时用 junction 实时同步共享目录更改 + skip-worktree 让 Git 忽略；提交时 pre-commit 自动转真实文件让 Git 感知改动并加入提交；提交后 post-commit 自动恢复 junction。
- **复盘结果：**
  - ✅ 日常改共享目录 → 项目实时同步（junction）
  - ✅ `git status` 日常不显示 junction 文件（skip-worktree）
  - ✅ `git commit` → pre-commit 自动转真实文件 → Git 感知改动 → 提交 → post-commit 恢复 junction
  - ✅ 手动切换：`.\sync-skills.ps1 -ToReal` / `-ToJunction`
  - ✅ `lania-agent-runtime` 非 Git 项目，junction 全自动

#### 2. Skill 规则合并至共享目录 + Git 兼容方案

- **时间：** 2026-07-24 12:30:00
- **发起人：** user
- **修改文件：**
  - `E:\vsc-workspace\lania-shared-skills\ai-coding-rules\` — 合并所有改动至共享中心
  - `E:\vsc-workspace\lania-shared-skills\sync-to-project.ps1` — 新增同步脚本
  - `prd2tsd-agents\.github\skills\ai-coding-rules` — 恢复为真实目录（Git 兼容），通过 `sync-to-project.ps1` 与共享目录同步
  - `lania-agent-runtime\.github\skills\ai-coding-rules` — Junction → `lania-shared-skills`（非 Git 项目，junction 自动同步）
  - `lania-agent-runtime\.github\copilot-instructions.md` — 新建
- **修改内容：** 共享目录合并完成后，发现 prd2tsd-agents 用 Junction 会导致 Git 显示文件被删除。已将 prd2tsd-agents 恢复为真实文件目录，新增 `sync-to-project.ps1` 同步脚本用于手动从共享目录同步到各项目
- **修改内容：** 将四层测试体系、真实环境验证、验证报告模板等改动合并到共享目录 `lania-shared-skills`；prd2tsd-agents 的 ai-coding-rules 从独立副本改为 Junction 链接，修改共享目录即自动同步所有项目
- **复盘结果：** 双向合并完成——共享目录获得了新规则（R10a/四层测试/验证报告），prd2tsd-agents 获得了共享目录的已有改进（R8b/R8c 设计文档 checklist、R10 功能可用性验证、各语言注释示例）
- **潜在风险：** 修改共享目录会影响所有通过 Junction 链接的项目，改动前需确认影响范围



#### 1. Skill 规则增强：强制真实环境连接验证（Smoke Test）

- **时间：** 2026-07-24 12:00:00
- **发起人：** user
- **修改文件：**
  - `.github/skills/ai-coding-rules/rules/00-base.instructions.md` — 新增 R10a 真实环境验证规则
  - `.github/skills/ai-coding-rules/rules/03-testing.instructions.md` — 重写为测试分层规范，增加 Smoke Test 强制要求
  - `.github/skills/ai-coding-rules/rules/01-typescript.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/08-dart.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/09-rust.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/10-python.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/11-go.instructions.md` — Testing 节增加真实环境验证
- **修改内容：** 新增全局规则 R10a，要求涉及外部服务的项目必须运行真实环境连接验证测试（禁止 Mock），确认服务可达后才能报告"测试通过"；03-testing 重写为四层测试体系（单元/集成/Smoke/E2E）；新增"验证报告"强制输出章节（含标准模板，必须按格式输出测试结论）；所有语言规则同步增加真实环境验证要求；E2E 测试通过为最终准入条件
- **复盘结果：** 解决了 AI 仅凭 Mock 测试通过就误报"全部成功"的问题，现在 Skill 强制要求：(1) 区分 Mock 测试与真实环境测试 (2) 测试结束后必须按模板输出结构化验证报告 (3) 所有外部服务 Smoke Test 必须 ✅ 正常 (4) 有完整环境时还需 E2E 测试通过才能报告"通过"
- **潜在风险：** 部分 CI/CD 环境可能没有外部服务运行中，需要配置条件跳过或标记为"环境不可用"
### 2026-07-23

#### 1. 块 A：基础设施与质量底座

- **时间：** 2026-07-23 14:30:00
- **发起人：** user
- **修改文件：**
  - 新增 42 个文件（见下方详表）
- **修改内容：** 搭建项目骨架、质量基础设施、数据模型、认证授权和多租户中间件、LLM Gateway 核心、模型配置中心、数据安全模块、CI/CD 流水线
- **复盘结果：** 所有基础设施容器（PostgreSQL/Redis/MinIO/Neo4j）正常运行，52 个单元测试通过，E2E 全链路 12/12 通过
- **潜在风险：** Neo4j 需企业版镜像，当前使用社区版；passlib 在 Python 3.14 不兼容，已改用 bcrypt 直接调用

**新增文件清单：**

```
├── pyproject.toml / requirements.txt / .gitignore
├── docker-compose.yml / Dockerfile
├── contracts/ (__init__, interfaces, models)
├── app/
│   ├── main.py
│   ├── core/ (config, connections, llm, logger, exceptions)
│   ├── llm_gateway/ (__init__, models, config_manager, provider, router, cost_tracker, cache)
│   ├── security/ (data_classifier, data_masking, audit_logger)
│   ├── models/ (base, user, organization, workspace, role, team_member)
│   ├── auth/ (token_manager, permissions, middleware, deps)
│   └── api/ (deps, routes/auth/workspace/model_config, schemas)
├── .github/workflows/ (ci, deploy-prod, backup)
├── alembic/ (env, script.py.mako)
├── scripts/ (init_db, e2e_test, ensure_tables, debug_login)
├── tests/ (conftest, 14 test files)
├── overview.md

### 2026-07-23

#### 2. 块 B：知识层（数据 + 检索）

- **时间：** 2026-07-23 18:30:00
- **发起人：** user
- **修改文件：**
  - `requirements.txt` — 新增 llama-index-core, llama-index-graph-stores-neo4j, llama-index-vector-stores-postgres, llama-index-embeddings-huggingface, sentence-transformers, pgvector
  - 新增 `app/knowledge_layer/` (24 个文件)
- **修改内容：** 构建知识图谱完整生命周期：模型定义 → 文档加载 → 多粒度分块 → LLM 实体提取 → 实体融合/消歧 → 实体 Embedding → Neo4j 实体 + PGVector 向量双写 → 检索管线（意图路由/重写/丰富/Local Search/Global Search/RRF 融合/重排/压缩）
- **复盘结果：** 79 个单元测试通过（含块 A 回归测试全绿），7 个集成测试通过（Mock 模式）
- **潜在风险：** BGE Embedding 模型首次加载较慢（~3min）；Neo4j/PGVector 集成测试需真实容器运行

#### 3. 块 B ↔ 块 A 联通性打通

- **时间：** 2026-07-23 20:00:00
- **发起人：** user
- **修改文件：**
  - `app/core/connections.py` — Neo4jConnector enabled=False → True（启动时自动连接）
  - `.env` — DATABASE_URL/NEO4J_URI 修复为 localhost
  - `app/api/routes/knowledge.py` — 新增（build / search 两个端点）
  - `app/main.py` — 挂载 knowledge_routes，注册知识层 API
  - `requirements.txt` — 新增 python-multipart
  - `scripts/e2e_test.py` — 扩展 2 个知识层测试步骤
- **修改内容：** 打通块 B 知识层与块 A 基础设施的全链路集成：Neo4j 启动时自动连接、知识层 API 路由挂载（Auth 中间件保护）、健康检查纳入 Neo4j 状态
- **复盘结果：**
  - E2E 14/14 ✅（块 A 12 项 + 块 B 2 项）
  - 单元测试 79/79 ✅（含全部块 A 回归）
  - 集成测试 7/7 ✅
  - Ruff 0 errors ✅
  - Neo4j 连接: `connected=true, latency=5ms`
  - PostgreSQL 连接: `connected=true, latency=6ms`
- **潜在风险：** mypy strict 模式在 `connections.py` 有 11 个已有类型错误（块 A 遗留）；知识层搜索 API 涉及 LLM 调用导致首次响应较慢

**新增文件清单：**

```
app/knowledge_layer/
├── __init__.py / config.py / models.py / pipeline.py
├── graph_store.py / vector_store.py
├── ingestion/
│   ├── __init__.py / document_loader.py / chunker.py
│   ├── entity_extractor.py / relation_extractor.py / entity_resolver.py
│   ├── claims_extractor.py / entity_embedder.py / text_unit_builder.py
│   ├── knowledge_aging.py / kg_versioning.py / index_builder.py
└── retrieval/
    ├── __init__.py / intent_router.py / rewriter.py / enricher.py
    ├── local_search.py / global_search.py / fusion.py / reranker.py / compressor.py

tests/
├── fixtures/sample_prd.md
├── unit/
│   ├── test_ingestion.py / test_entity_resolver.py / test_claims_extractor.py
│   ├── test_knowledge_aging.py / test_kg_versioning.py
│   └── test_local_search.py / test_global_search.py
└── integration/
    ├── test_kg_build.py / test_kg_versioning_integration.py
    ├── test_local_search_integration.py / test_global_search_integration.py
```
