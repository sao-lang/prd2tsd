# PRD2TSD 3.1–3.15 功能链路面试详解

> 本文是 `interview-prep-complete.md` 第 3 章的展开版。目标是让非项目原作者也能在面试中讲清楚：请求从哪里进入、数据如何流转、为什么这样设计、失败时如何降级。本文以当前源码为准，不把尚未闭环的设计目标描述成已完成能力。

## 0. 先记住整体分层

```text
接入层：统一 API、认证、文档和 URL 接入
        ↓
编排层：LangGraph 主图、状态、人工审核、断点恢复
        ↓
业务子图：Analysis → Planning → Generation → Evaluation
        ↓
知识层：文档入图、图检索、向量检索、反思与重排
        ↓
模型基础设施：Gateway、护栏、限流、路由、预算、缓存、熔断、Failover、成本
        ↓
支撑能力：会话记忆、SSE、可观测性、数据库和对象存储
```

面试时先讲业务主链，再根据追问深入 Gateway、知识检索、并行生成或人工审核，不需要一次把全部细节倒出来。

## 3.1 统一交互入口与意图分类链路

### 链路解决什么问题

历史上聊天、问答、生成和文档分析分别使用不同接口，前端需要理解后端业务。现在统一为 `POST /api/v1/interact`，由服务端识别意图并选择执行链路。

### 完整流程

```text
POST /api/v1/interact
  → AuthMiddleware 解析 JWT
  → WorkspaceContextMiddleware 注入工作空间
  → Pydantic 校验 InteractRequest
  → URL/doc_id 强信号判断
  → 规则意图分类
  → 规则置信度是否 ≥ 0.8
      ├─ 是：直接采用规则结果
      └─ 否：gateway.complete(task_type="intent_classify")
             → 输入护栏/脱敏 → workspace 限流与预算
             → 意图分类路由 → 熔断/Failover → 输出护栏
             → 解析 intent、confidence、sub_intent
  → 根据 intent + stream 分流
      ├─ chat / knowledge_qa → 主图或流式问答
      ├─ clarification → 澄清节点
      ├─ complex_generation → TaskManager 异步任务
      └─ document_analysis → 文档/URL 分析
```

意图类型包括 `chat`、`knowledge_qa`、`complex_generation`、`clarification` 和 `document_analysis`。如果请求携带 `url` 或 `doc_id`，直接按文档分析处理；否则先匹配生成、文档分析、知识问答和闲聊关键词。规则结果置信度达到 0.8 就直接采用，低置信度再通过 `gateway.complete(task_type="intent_classify")` 分类，既减少常见请求的模型成本，也保留对模糊表达的识别能力。

请求模型在进入路由函数前由 Pydantic 校验：`message` 至少 1 个字符；`prd_type` 只允许 md/pdf/docx/txt；Provider 最长 64、模型名最长 128；`estimated_tokens` 不能为负；`max_tokens` 范围是 1～131072；单次 timeout 范围是 0～600 秒。`_gateway_overrides()` 只把非空覆盖项放进字典，未提供 max_tokens 时各业务分支再使用自己的默认值，避免请求 Schema 中的空值覆盖 Gateway 路由配置。

规则分类有明确顺序和分数：生成关键词优先，命中即为 complex_generation/0.85；文档分析关键词次之，同样为 0.85；知识问答命中两个及以上关键词为 0.9，只命中一个为 0.7；闲聊命中为 0.8；少于 8 个字符的短输入先给 knowledge_qa/0.6。0.7、0.6 这类低分结果才会和 LLM 结果比较，只有 LLM confidence 更高才覆盖；LLM 异常或 JSON 无效时最终默认 complex_generation/0.5。LLM 分类只带最近 3 条历史，每条最多 200 字符。

同步模式下，普通对话返回 JSON；复杂生成只创建任务并立即返回 `task_id`。流式模式统一返回 `text/event-stream`，但不同意图使用不同事件，如 `qna.chunk`、`analysis.chunk` 和 `task.progress`。

同步分发并不等于所有请求都同步跑完整图：document_analysis 直接读取文档或 URL 后调用分析模型；complex_generation 调用 TaskManager 后立即返回；chat、knowledge_qa、clarification 才构造 UUID task_id，并以同一个值作为同步图的 thread_id 调用 `orchestrator.ainvoke()`。如果这条短图整体异常，路由会降级为 `gateway.complete(task_type="chat", temperature=0.7, max_tokens=1024)`，因此返回 intent 会降成 chat/0.5。

流式分发也有三套执行器：普通 chat/QA 在 HTTP generator 内完成检索并直接遍历 `gateway.stream_complete()`；复杂生成先创建后台任务，再订阅 `task:{task_id}`；文档分析使用 `analysis.status/analysis.chunk`，而 `generate=true` 的 URL 请求会转为复杂任务并切换到 task 事件。也就是说“统一入口”统一的是请求协议和意图分发，不代表内部强行共用同一执行函数。

API 层已确定意图时，会把 `intent`、`intent_confidence` 和 `intent_sub` 预写入 `OrchestratorState`。图内 `classify` 节点发现状态已有 intent 就跳过，避免重复调用分类器。

### Gateway 在这里的作用

规则分类本身不调用模型；只有规则不确定时才进入 Gateway。Gateway 先从请求的 `ContextVar` 取得 workspace、Provider/模型覆盖、timeout 和 Token 估算，再执行输入护栏、RPM/TPM 预留、预算检查、缓存查询与模型路由。主 Provider 超时、异常或已熔断时尝试备用 Provider，成功结果通过输出护栏后记录 Token、成本和指标。因此意图识别不会成为绕开统一模型治理的特殊入口。

这里的“幂等”不是指重复请求一定只执行一次，而是指分类结果已经写进 `OrchestratorState` 后，图内分类节点看到已有结果就不再分类。真正的 HTTP 请求去重还需要客户端幂等键或服务端请求记录，当前链路没有把它当作已实现能力。

### 当前实现边界

- 普通同步请求会把已识别 intent 写入主图；复杂生成交给 TaskManager 后会重新构造初始状态，异步路径仍可能在图内再次分类。
- 流式聊天/问答主要走专门的流式函数，不完全等同于同步模式的主图执行路径。
- 请求支持 Provider、模型、超时和 Token 估算等单次覆盖，通过 `ContextVar` 传给后台异步任务。

### 面试话术

> 我把它理解成业务层的统一入口。服务端先用强信号和规则做低成本分类，不确定时再调用 LLM Gateway。分类后，短请求同步返回，PRD 转 TSD 这种长请求异步返回 task_id，流式请求走 SSE。API 已识别的 intent 会写入状态，让图内分类节点幂等跳过，从而减少重复判断。

常见追问：

- __为什么不全部用 LLM 分类？__ 强规则处理 URL、doc_id 和明显关键词更快、更便宜，也更可预测；LLM 只补规则覆盖不到的模糊表达。
- __规则和 LLM 结果冲突怎么办？__ 强信号优先，普通规则达到阈值也直接采用；只有低置信度结果交给 LLM，避免两套分类器来回覆盖。
- __为什么复杂任务只返回 task_id？__ Analysis 到 Evaluation 有多次模型调用、人工中断和重试，持有 HTTP 请求容易超时；task_id 让状态查询和 SSE 订阅与后台执行解耦。

关键文件：`app/api/routes/interact.py`、`app/api/schemas/interact.py`、`app/orchestrator/intent_classifier.py`、`app/orchestrator/nodes/intent_classify.py`。

---

## 3.2 主编排图与复杂生成主链路

### 链路解决什么问题

PRD 转 TSD 不是一次 Prompt 能稳定完成的任务。主编排图把它拆成可观察、可审核、可恢复、可迭代的状态机，并通过统一状态串联四个业务子图。

### 完整流程

```text
/interact 判定 complex_generation
  → TaskManager 创建 task_id、thread_id 和任务记录
  → asyncio.create_task 启动后台执行
  → make_initial_state 构造 OrchestratorState
  → orchestrator.astream(initial_state, thread_id)
  → inject_runtime
  → classify
  → retrieve_memory
  → knowledge_retrieval
  → AnalysisAdapter → Analysis 子图
  → Analysis 人工审核
  → PlanningAdapter → Planning 子图
  → Planning 人工审核
  → GenerationAdapter → Generation 子图
  → EvaluationAdapter → Evaluation 子图
  → IterationDecider
      ├─ 通过 → final_assembly
      ├─ 重新规划 → planning
      ├─ 重新生成 → generation
      └─ 严重问题 → analysis_human_review
  → compress_memory
  → save_session
  → END
```

`task_id` 是业务任务标识，用于查询状态和订阅 SSE；`thread_id` 是 LangGraph 执行标识，用于 checkpoint、interrupt 和 resume。两者分开可以让业务任务生命周期与图运行状态各自演进。

主图共有 16 个节点，但其中包含 chat、knowledge_qa、clarification 等短路径节点，不代表一次复杂生成必然执行 16 个节点。

四个 Adapter 负责在 `OrchestratorState` 和各层 `LayerState` 之间转换：提取子图需要的输入，调用子图，再把结果映射回主状态。它们同时推进显式进度：知识检索 0.10、分析 0.25、规划 0.50、生成 0.75、评测 0.90、最终组装 1.0。

主状态里贯穿全链路的字段可以分成四类：身份类（task_id、workspace_id、session_id、user_id）、输入类（prd_raw、prd_file_type、intent）、阶段产物类（knowledge_context、analysis_result、planning_result、generation_result、evaluation_report）和控制类（progress、iteration_count、max_iterations、status、error_message）。Adapter 的价值就是只把本层需要的字段映射进子图，避免四个子图共同修改一个巨大状态对象。

准确地说，`thread_id` 不在 `OrchestratorState` 中，而是在 LangGraph 调用配置 `{"configurable": {"thread_id": ...}}` 中；TaskManager 自己的任务记录同时保存 task_id 和 thread_id。State 中实际包含 task/workspace/user/role/permissions、TenantContext、四层产物、section_contents/export_formats、iteration/status/error/progress，以及可选的 intent 和记忆字段。运行时数据库会话、EventBus、Gateway 引用放在 `OrchestratorRuntime`，不进入 checkpoint，避免序列化连接对象。

TaskManager 创建任务时生成两个 UUID，在 `asyncio.Lock` 下写入内存字典，再把可恢复索引持久化到 task store，发布 `task.created`，最后用 `asyncio.create_task()` 启动 `_execute_task()`。后台执行通过 `orchestrator.astream(initial_state, config)` 消费每个节点产生的状态更新；只要读取到正进度就发布 `task.progress`。图正常完成后提取 generation_result/evaluation_report 写回任务记录；抛异常则标记 failed；检测到 interrupt 则写 paused 和 interrupt_stage，等待审核接口恢复。

主图的入口 `inject_runtime` 先把当前请求运行时挂到线程级注册表，再进入 classify。复杂生成路径的知识检索只拿 `prd_raw[:500]` 做 query，失败时把 knowledge_context 设为 None 并继续。四个 Adapter 分别调用子图的 `ainvoke()`：Analysis 回填需求和约束；Planning 回填组件和技术栈；Generation 回填章节和导出结果；Evaluation 回填报告并把 iteration_count 加 1。FinalAssembly 本身不重新生成内容，只把 status 设为 complete、progress 设为 1.0，结束 DecisionRecorder，并尝试发送完成 Webhook；Webhook 异常只记录告警。

评测默认通过线是 85 分、重规划参考线是 70 分、最多评测 3 轮。高分进入最终组装；中间分根据一致性和可行性决定重新生成或规划；低分且有严重问题时转人工介入。

### LLM Gateway 如何贯穿主图

各子图节点不直接依赖某个 Provider SDK，而是通过 `GatewayChatModel` 或 `gateway.complete/stream_complete` 调用。典型调用链为：

```text
业务节点构造 Prompt
  → GatewayChatModel 把 LangChain messages 转为 Prompt
  → 解析 workspace/task_type/Provider/模型/timeout/max_tokens
  → 估算输入 Token + 最大输出 Token
  → 前置护栏与可逆脱敏
  → workspace 级 60 秒滑动窗口预留 RPM/TPM
  → 周/月预算检查，必要时切低成本路由
  → 精确缓存 → 向量语义缓存（默认相似度 0.92、TTL 1 小时）
      ├─ 命中：返回缓存内容
      └─ 未命中：按 task_type 选择主 Provider/模型
  → Failover 只读熔断状态并按优先级过滤候选
      ├─ 可用：由 CircuitBreaker.call 在 timeout 内调用
      └─ OPEN/超时/异常：跳过或按 fallback 顺序切备用 Provider
  → 恢复脱敏值并执行后置护栏
  → 写语义缓存、Token、成本、预算账本、Prometheus 和 Trace
  → 用实际 Token 校正限流预留
```

路由规则按 `task_type` 区分 Analysis、Planning、Generation、Evaluation 和 Vision 等任务，配置优先级是运行时配置、环境配置、默认配置。熔断器按 Provider 隔离：连续失败 3 次后打开，30 秒后进入 HALF_OPEN 探测；熔断解决“暂时别再请求故障服务”，Failover 解决“当前请求换谁继续完成”，两者配合但职责不同。

一次非流式调用的真实顺序是“先解析路由和估算 Token，再进入 CLIENT span，随后前置护栏、限流预留、预算降级、缓存、Failover、后置护栏、计费与校正”。这里有几个容易被追问的细节：护栏拦截和限流不是抛异常，而是返回带 metadata 的零成本 `LLMResponse`；所有 Provider 都失败时返回固定的“服务暂不可用”；缓存命中把预留 Token 校正为 0；真实调用成功后才把 Provider 返回的 usage 写进 Token 指标、成本表和预算账本。业务节点因此仍要判断 metadata/内容，不能把“Gateway 返回了对象”等同于模型成功。

`FailoverManager` 为每个 task_type 路由组装“主 Provider/模型 + fallback 列表”，目标对象不保存健康状态。它只通过 `CircuitBreakerManager` 读取 `is_available` 并返回候选；真正的 Provider 调用由 `breaker.call()` 包裹并受 `asyncio.timeout()` 约束。只有 CircuitBreaker 会在异常时增加连续失败数、在成功时清零、在恢复窗口到期后控制 HALF_OPEN 试探。熔断器由 `provider:{provider_name}` 命名，因此同一 Provider 下不同模型共享健康状态；默认阈值为 3、恢复等待 30 秒、HALF_OPEN 最多放 1 个探测请求。

缓存范围包含 workspace、task_type、模型、Prompt 和 guardrail 版本，避免跨租户串数据，也避免安全策略升级后继续返回旧版本结果。限流按 60 秒窗口同时约束 RPM 和 TPM，调用前用 Prompt 长度与 `max_tokens` 做预留，调用后按真实 usage 校正；预算则根据 PostgreSQL 中的调用账单按周/月统计，控制的是更长周期成本。

缓存是两级的。一级是进程内 dict，精确 key 为 `SHA256(workspace::task_type::model::guardrail_version::输入身份)`，默认最多 1000 条，满了删除时间最老的一条；二级从 PostgreSQL 只读取同 workspace、task_type、模型、Embedding 模型和护栏版本且未过期的候选，最多比较配置的候选数，再用余弦相似度选最高项，达到默认 0.92 才命中。匿名调用没有 workspace 时只允许一级精确匹配。多模态请求会把图片载荷 SHA-256 纳入输入身份，并禁用只看文本 Prompt 的语义匹配，防止不同图片因 OCR 指令相同而串缓存；纯文本仍使用两级语义缓存。

限流记录结构是 `{workspace_id: [(monotonic时间, 预留Token, reservation_id)]}`。`reserve()` 先做一次快速 check，再在 `threading.Lock` 内清理 60 秒外记录并重新计算 RPM/TPM，解决并发请求都在 check 阶段看到“还有配额”的竞态；允许后立即占一条请求和估算 Token。`reconcile()` 找到 reservation_id 后用实际输入加输出 Token 替换估算值，找不到则补记。它是单进程内存限流器，横向部署时各 Worker 各有一份窗口，生产环境应换成 Redis/Lua 等跨实例原子实现。

预算与限流不是同一个概念：限流防一分钟内的突发流量，预算控制周/月累计费用。BudgetController 从 PostgreSQL 的 budget_configs 读取 workspace 配置，再汇总 llm_call_logs 当前周期成本，超过告警阈值时要求切到低成本模型；调用完成后写入实际模型、输入/输出 Token、layer、node 和 cost。当前降级映射只明确覆盖 `gpt-4o-mini → openai`、`deepseek-chat → deepseek`，其他低成本模型默认按 openai Provider 处理，新增 Provider 时要同步扩展映射。

默认 7 类护栏不是简单的七次关键词判断：PromptInjectionGuardrail 检测越权和指令覆盖；PIIDetectorGuardrail 识别并掩码敏感信息；TimeoutGuardrail 检查调用期限和熔断状态；ContentSafetyGuardrail 检查不安全输出；OutputValidatorGuardrail 校验基本输出格式；EmptyResponseGuardrail 标记空响应；RetryDecisionGuardrail 根据错误上下文给出重试建议。结构化业务节点还会在 Gateway 之后叠加 Pydantic 解析，这是业务 Schema 校验，不和安全护栏混为一层。

七项护栏按注册顺序串行执行，前置护栏遇到 blocked 立即停止，后置护栏只有 critical blocked 才停止。PromptInjection 先做 NFKC、casefold、去零宽字符和压缩空白，再用中英文正则累计风险分；单个权重 4 的高置信信号或总分达到阈值直接拦截。PII 检测用正则识别身份证、手机号、银行卡和邮箱，统一替换为 `[PII_MASKED]`，随后 MaskingEngine 还对 L3 数据做可逆脱敏；Provider 返回后先还原 token，再进行输出安全检查，防止还原出来的密钥绕过后置护栏。

TimeoutGuardrail 的名字容易误导：它本身不包裹网络超时，而是在调用前检查 timeout 是否已耗尽，以及 Failover 链是否至少有一个熔断器可用；真正的 Provider 超时由调用阶段的 timeout 控制。ContentSafety 用正则检查 API key、secret、password、token 和 PEM 私钥并掩码。OutputValidator 仅在显式 response_format 或 task_type 含 `json` 时尝试 `json.loads()`，会剥离 Markdown JSON 围栏；解析失败只是 warning，不会自动修复。EmptyResponse 也只返回 warning。

当前 `RetryDecisionGuardrail` 虽然定义了空响应、JSON 错误、超时和最多 3 次的判断，但 `_guard_output()` 没有把 `error_type`、`retry_count` 和前序结果传给它，也没有依据它的结果发起新调用；因此现状中的真正重试能力主要来自 Provider Failover 和上层 Celery/图重跑，不能说七号护栏已经自动完成三次重试。这是面试时非常好的“设计意图与当前接线差距”示例。

`complete()` 在治理完成后一次返回。`stream_complete()` 也走相同限流、预算、缓存、路由和护栏，但当前会先缓冲单个 Provider 的完整输出，后置护栏通过后再释放 chunk；如果主 Provider 中途失败，其半截内容会被丢弃，再从备用 Provider 重新生成。安全和结果一致性更强，代价是首包延迟增加。

### 面试话术

> 主编排图负责阶段顺序和状态流转，子图负责本领域任务，Gateway 负责所有模型调用的安全、稳定性和成本。这样图不会绑定某个模型厂商，各层也可以独立测试。长任务通过 task_id 对外跟踪，通过 thread_id 和 checkpointer 实现暂停恢复，评测不通过时还能按问题类型回到规划或生成阶段。

常见追问：

- __为什么是主图加子图，而不是一个大图？__ 主图只负责跨阶段路由和生命周期，子图封装本领域状态与节点；这样 Analysis 或 Generation 可以独立测试和替换。
- __Adapter 是不是多余的一层？__ 它隔离 `OrchestratorState` 与各层 State，明确字段映射、进度和错误边界，否则所有节点都会耦合主状态结构。
- __熔断和 Failover 有什么区别？__ 熔断按 Provider 记录健康状态并快速拒绝故障目标；Failover 在一次请求内按备用链换 Provider。没有熔断会反复撞故障服务，没有 Failover 则熔断后请求只能失败。
- __缓存为什么还要带 guardrail 版本？__ 护栏规则更新后，旧缓存可能不再符合当前安全要求；把版本放进隔离维度可以自然失效旧策略结果。
- __限流为什么要先预留再校正？__ 并发请求开始时还没有真实 usage；如果都等结束再记账，会同时穿透 TPM。先按输入估算和 max_tokens 占位，结束后替换成真实值，可以控制突发并减少长期误差。
- __七项护栏是不是都会自动重试？__ 不是。当前 Prompt 注入和无可用熔断器会直接拦截，PII/密钥会脱敏，JSON/空响应主要产生检查结果；RetryDecision 尚未接成自动重试循环，实际容错依赖 Gateway Failover 和业务层重跑。
- __语义缓存会不会把 A 租户答案给 B 租户？__ 候选查询和精确 key 都含 workspace、task_type、模型、Embedding 模型及护栏版本；没有 workspace 时直接禁止持久化语义命中，只保留本进程精确缓存。

关键文件：`app/task_manager.py`、`app/orchestrator/main_graph.py`、`app/orchestrator/state.py`、`app/orchestrator/adapters/*.py`、`app/llm_gateway/__init__.py`。

---

## 3.3 知识图谱构建（Ingestion）链路

### 链路解决什么问题

把上传文档或网页正文加工成两类可检索知识：Neo4j 中的技术实体与显式关系，以及 PGVector 中的原文块、实体和 Claims 向量。

### 完整流程

```text
文件字节/网页文本
  → multi_format_loader 提取文本
  → paragraph 级分块
  → EntityExtractor 逐块构造 Prompt
  → gateway.complete(default)
      → 护栏/限流/预算/缓存 → 主模型或 Failover → JSON 解析
  → 得到 TechStack/Component/Pattern/Constraint/Concept
  → 与当前 workspace 已有实体做消歧合并
  → RelationExtractor 按 Chunk 从候选实体间抽取关系并校验端点
  → gateway.embed(embedding) 为实体生成向量
  → 实体与 RELATED 关系写入 Neo4j
  → ClaimsExtractor + claim_embeddings（文件、上传和 URL 共用）
  → gateway.embed → text_unit_embeddings
  → gateway.embed → entity_embeddings
  → 返回 entities/relations/chunks/claims 统计
```

### 每一步的数据变化

#### 1. 文件字节怎样变成统一文本

上传链调用 `build_from_bytes(content, filename, workspace_id, document_id)`。方法先根据文件名最后一个 `.` 取得小写扩展名，再分别调用 `multi_format_loader.extract_text()` 和 `extract_images()`。这里没有通用的“智能解析器”，而是按扩展名进入明确分支：

| 文件类型 | 当前解析方式 | 产生的文本 |
| --- | --- | --- |
| `.md` / `.txt` | `content.decode("utf-8", errors="replace")` | 原文本基本原样保留；非法 UTF-8 字节替换为替代字符，不做编码探测 |
| `.csv` / `.tsv` | 标准库 `csv.reader`，分隔符分别为逗号和 Tab | 每行去掉空单元格和首尾空白，转换成 `记录: 单元格1，单元格2。`；表头不会被特殊识别 |
| `.docx` | `python-docx` 读取段落/表格；ZIP `word/media/*` 提取图片 | 正文 + 每张内嵌图片的 Gateway Vision OCR，来源标记为 DOCX 图片名 |
| `.pdf` | `pypdf` 逐页提取文字，并遍历 `page.images` | 页文本 + 页内栅格图片 OCR，来源保留 PDF 页码和图片名 |
| `.png` / `.jpg` / `.jpeg` | Pillow 校验/规范化后调用 `gateway.analyze_vision()` | 元数据 + 可见文字逐字转录 + 图表、流程、截图等语义描述 |

`build_from_bytes()` 先执行确定性正文提取，再执行 `extract_images()`。图片按内容 SHA-256 去重，受单文档 50 张、单图 20MB、图片总量 50MB 的默认限制；OCR 提示明确把图片文字当作不可信数据，禁止执行图中指令。每张图片使用独立 `vision` 路由并传入预计 Token，OCR 被护栏拦截、限流、全部 Provider 失败或返回空内容都会抛错，使 Celery 将任务标为 failed 并重试，而不是把错误响应写进知识库。最终正文与 `[图片 OCR：来源]` 段落合并后才进入 `build_from_text()`。本地路径入口对非 Markdown 文件也会转到同一字节流链路；Markdown 保留原有完整构建路径。

#### 2. paragraph 分块具体怎样做

`KnowledgeGraphBuilder` 用配置创建 `MultiGranularityChunker(sentence_max_words=50, paragraph_max_words=500)`，但主链固定调用 `chunk(text, level="paragraph")`。具体逻辑是：

1. 使用正则 `\n\s*\n` 按“空行”切段，即两个换行之间即使只有空格也视为段落边界。
2. 对每段执行 `strip()`，空段直接丢弃。
3. 代码变量虽然叫 `words`，实际用的是 `len(para)`，所以 500 的单位是 Python 字符数，不是英文单词数，也不是 Token 数。
4. 不超过 500 字符的段落直接生成一个 `Chunk`。
5. 超过 500 字符时，再用 `(?<=[。！？])\s*` 按中文句号、问号、感叹号切句，逐句加入 buffer；加入下一句会达到或超过 500 时，先把现有 buffer 输出，再开一个新 buffer。
6. 每个 Chunk 使用 `uuid4()` 生成随机 ID，写入 `text`、`level="paragraph"` 和顺序 `index`；paragraph 模式下 `section_path` 为空、`metadata` 默认空字典。

这里有两个面试时值得主动说明的边界。第一，英文句号不在二次切分规则中，一个没有中文句末符的超长段落仍可能大于 500 字符，因此这不是严格 Token 上限。第二，上传链的 `document_id` 不写进 Chunk 对象，而是在 `upsert_chunk()` 落 PGVector 时单独写入；Chunk 自己只通过随机 ID和后续实体的 `source_text_unit_id` 建立来源关联。

分块器也实现了 sentence 和 section 模式：sentence 用 `。！？` 或换行切句，超长句再按 `，；` 切；section 只识别行首 1～3 级 Markdown 标题，并把 `# 标题` 保存进正文、把标题层级写入 `section_path`。当前入图主链并没有调用这两个模式，面试时可说“能力存在，但实际使用 paragraph”。

#### 3. 实体和 Claim 怎样从 Chunk 中提取

`EntityExtractor.extract()` 按 Chunk 列表顺序逐个 `await`，当前不是并行批处理。每个 Chunk 只取 `chunk.text[:2000]` 填入 Prompt，要求模型返回 JSON 数组，并限定五种实体类型：`TechStack`、`Component`、`ArchitecturePattern`、`Constraint`、`Concept`。Gateway 调用参数为 `task_type="default"`、`layer="knowledge"`、`node="entity_extractor"`、`temperature=0.1`、`max_tokens=2048`。

Gateway 完成输入护栏、限流、预算、缓存、路由、熔断和 Failover 后，Extractor 会去掉可能存在的 ```json 代码围栏，再用 `json.loads()` 解析。只有顶层为数组才继续；调用异常、JSON 无效或返回对象而不是数组时，该 Chunk 返回空实体，不会中断其他 Chunk。有效元素转换为 `KGEntity`：ID 为新 UUID，名称为空的丢弃，类型缺省为 `Concept`，置信度使用模型默认值 0.9，并把来源 Chunk ID 写入 `source_text_unit_id`。

`ClaimsExtractor` 采用几乎相同的逐块流程，同样只看前 2000 字符、温度 0.1、最大输出 2048。它提取 `decision`、`specification`、`constraint`、`comparison`、`prediction` 五类断言，只有 `subject` 和 `content` 同时非空才保留，并保存 `object` 与来源 Chunk ID。`build_from_document()`、上传字节流与 URL 最终统一进入 `build_from_text()`，所以三类入口都会执行 Claims 提取；Claim ID 根据 workspace、来源、类型、主客体和内容生成稳定 UUID，并尽量绑定消歧后的实体 ID。

`RelationExtractor` 只在同一 Chunk 至少有两个候选实体时调用 Gateway。Prompt 明确禁止创造端点，返回结果还会再次校验 source/target 是否属于该 Chunk 的候选实体，并映射到消歧后的稳定实体 ID；幻觉端点、自环和无 ID 端点会被丢弃。关系类型会规范为最长 64 字符的安全小写标识，关系 ID 由 workspace、源实体 ID、关系类型、目标实体 ID 生成稳定 UUID。

#### 4. 实体消歧和向量具体怎样生成

Builder 先从 Neo4j 拉取当前 workspace 最多 10000 个已有实体，再把新实体交给 `resolve_touched_batch()`。匹配顺序是：名称 `lower().strip()` 精确相等；固定别名表匹配，例如 PostgreSQL/Postgres/pg、Kubernetes/k8s；最后去掉连字符、下划线和空格后比较标准化 key。命中时保留已有实体 ID，用更长的描述覆盖短描述、取更高置信度并合并 properties；未命中才保留新 UUID。

`resolve_touched_batch()` 只返回本次命中或新增的实体，后续也只对这些实体重新生成 Embedding 和 upsert。这样既让 BuildStats.entities 表示本次处理数量，也避免无关历史实体的 `updated_at` 被刷新、永远无法进入老化阶段。原 `resolve_batch()` 仍保留兼容语义，但主构建链不再使用。

实体向量不是简单拼接文本一次 Embedding。`embed_entity()` 分别收集名称和描述，一次调用 `gateway.embed(texts=[name, description], task_type="embedding")`，两路权重各 0.5，再按维度做加权平均；如果只有名称，权重归一化后相当于名称占 100%。API Embedding 失败时延迟加载 `BAAI/bge-large-zh-v1.5`，默认在 CPU 上执行并做归一化；本地模型仍不可用才返回长度 1024 的零向量。Chunk 和 Claim 则用 `embed_text()` 单条生成。虽然类中存在 `embed_texts()` 批量接口，当前 Builder 的循环仍然是一条条调用和写库，吞吐量还有优化空间。

#### 5. Neo4j 和 PGVector 怎样落库

Neo4j 的实体写入也是逐条执行。`MERGE (e:KGEntity {id: $id})` 以实体 ID 为唯一匹配条件，再覆盖 name、type、category、description、properties、confidence、workspace_id、source_text_unit_id 和 updated_at；再次写入会恢复 `active` 并清除归档/删除时间。关系使用固定 Neo4j 类型 `RELATED`，业务 `relation_type` 作为参数化属性保存，避免把 LLM 输出拼接进 Cypher；写入前按实体 ID 和 workspace 同时匹配两端，缺任一端会明确失败。

PGVector 首先执行 `CREATE EXTENSION IF NOT EXISTS vector`，并确保三张表存在：

- `text_unit_embeddings`：Chunk 原文、1024 维向量、section_path、document_id、workspace_id。
- `entity_embeddings`：实体名称、类型、描述、向量、workspace_id。
- `claim_embeddings`：subject、claim_type、content、object、来源 Chunk、workspace_id 和向量。

三类写入均采用 `INSERT ... ON CONFLICT(id) DO UPDATE`，并且当前每条记录单独 `commit()`。实体消歧后 ID 稳定时可更新，Claim 已使用内容派生的稳定 UUID；Chunk 仍使用随机 UUID，重新入图仍可能产生重复块。Neo4j 与 PostgreSQL 之间也没有分布式事务：例如 Neo4j 成功、PGVector 失败时会形成部分完成，外层 Celery 虽会把任务标记失败并最多重试 3 次，但生产化还应增加阶段状态和补偿清理。

这条链通常在 Celery Worker 内执行：原文件已经先存入 MinIO，所以模型、Neo4j 或 PGVector 暂时失败时可以凭 document_id 重新下载并重跑，不要求用户重新上传。`workspace_id` 被写入 Neo4j 和三张向量表，并传给实体、关系和 Claims 的 Gateway 调用，使缓存、限流、预算和成本也按 workspace 隔离。

### 为什么双写 Neo4j 和 PGVector

- Neo4j 擅长表达实体及邻接关系，适合按实体查局部上下文。
- PGVector 擅长语义相似度，适合用户表达与原文不完全一致的查询。
- 两条检索路在读取阶段用 RRF 合并，互相弥补关键词和语义召回缺陷。

### 当前实现边界

- 关系抽取与 upsert 已闭环，但关系只从同一 Chunk 已识别的实体候选中抽取；跨 Chunk 关系、关系向量和关系本体约束尚未实现。
- `downgrade_days=90`、`archive_days=180`、`soft_delete_days=365` 已由每日 `refresh_knowledge_graph` 执行。任务按软删除→归档→降级处理实体和关系，检索只读取 `active/downgraded`，再次摄取会激活知识；历史无时间戳节点会先安全回填，当前老化依据是最后写入时间，还没有访问热度或业务保留标签。
- 文件路径、上传/Celery 与 URL 已统一走 `build_from_text` 的实体、关系和 Claims 步骤；Chunk ID 仍随机，重复重建的 Chunk 幂等性仍可加强。

### 面试话术

> 入图不是简单做 Embedding，而是先解析和分块，再抽取、消歧技术实体，从受约束候选中抽取显式关系，同时保留原文 Chunk 和结构化 Claim。Neo4j 保存实体与固定 `RELATED` 关系，PGVector 保存三类语义向量；每日 Celery Beat 还会按 90/180/365 天执行降级、归档和软删除。所有文件、上传和 URL 入口复用同一核心构建链。

常见追问：

- __为什么先分块再抽取？__ 整篇文档可能超过上下文且主题混杂；段落块能控制 Token、提高抽取聚焦度，并保留 Claim 到原文的来源定位。
- __实体消歧怎么做？__ 当前以规范化名称精确匹配和别名匹配为主，命中后合并属性、描述和置信度；还不是向量相似度或图上下文驱动的高级实体对齐。
- __写 Neo4j 和 PGVector 会不会不一致？__ 两边不是分布式事务，任一步失败都可能造成部分完成；当前依靠任务失败和重新入图恢复，生产化应增加阶段状态、幂等 upsert 和补偿任务。
- __Embedding 失败为什么还能继续？__ 原文件与结构化实体仍有价值，返回零向量是一种可用性降级；但零向量不能视为正常索引，应通过状态和监控安排重建。

关键文件：`app/knowledge_layer/pipeline.py`、`app/knowledge_layer/ingestion/*.py`、`app/knowledge_layer/graph_store.py`、`app/knowledge_layer/vector_store.py`。

---

## 3.4 检索链路（含反思循环）

### 链路解决什么问题

针对不同问题组合图检索、向量检索和宏观总结，并让 LLM 判断检索结果是否足够；不足时自动改写查询再检索。

### 完整流程

```text
用户查询 + workspace_id
  → IntentRouter：local / global / hybrid
  → QueryRewriter 经 Gateway：原问题 + 最多 4 个改写，最终最多 5 条
  → QueryEnricher：关键词匹配 Neo4j 实体
  → 进入反思循环（最多配置轮数）
      ├─ Local 图路：实体匹配 → 1~2 跳邻居 → ScoredDoc
      ├─ Vector 路：gateway.embed → PGVector cosine search
      └─ Global 路：workspace 实体按类型聚合 → Gateway 总结
  → RRF 融合多路排名
  → ReflectionJudge 经 Gateway：accept 或 refine_query
  → 不满足则用 refined_query 再检索
  → 本地 Cross-encoder 重排，失败则关键词混合打分
  → 压缩到约 4000 Token
  → RetrievalContext
```

### 各检索组件怎样协作

#### 1. 路由与查询改写

`retrieve(query, mode="hybrid", top_k=10, workspace_id="")` 的第一步不是 LLM 分类，而是 `IntentRouter` 关键词规则。只有传入的 mode 等于 `hybrid` 时才执行自动判断；如果调用方传 local 或 global，则直接采用指定值。路由优先检查全局关键词，例如“整体、架构、总结、overview”；再检查局部关键词，例如“如何、技术栈、组件、接口”；字符长度小于 5 的查询也判为 local，其他情况才返回 hybrid。因为 global 规则先执行，“整体架构”这类同时命中两组的查询会优先走 global。

`QueryRewriter` 把原问题放入 Prompt，要求生成 3 条不带编号的改写，Gateway 参数是 `task_type="default"`、`layer="knowledge"`、`node="query_rewriter"`、温度 0.3、最大输出 512。返回后按换行拆分、去掉空行，把原问题放在列表第一个，只过滤与原问题忽略大小写后完全相等的行，最终截取前 5 条。它不会清理模型返回的 `1.`、`-` 等编号，也不会在改写之间做语义去重；调用异常时直接返回 `[原查询]`。

`QueryEnricher` 用 `[a-zA-Z0-9_\-\u4e00-\u9fff]+` 提取连续关键词，长度小于 2 的跳过；每个关键词在 Neo4j 中执行 `e.name CONTAINS $query`，每词最多取 3 个实体，并按实体 ID 去重。命中后把前 5 个实体 ID拼成 `原查询 (entities: ...)`。当前 Pipeline 虽然得到了 `enriched_query` 和 `matched_entity_ids`，后面的 Local/Vector/Global 仍主要使用原 query 或 sub_queries，因此“实体链接已做，但增强结果尚未真正驱动召回”。另外，这个正则不会做中文分词，一整段连续中文可能被当作一个关键词。

#### 2. Local 图检索

Local 路最多消费重写列表的前 3 条，并按顺序逐条调用 `search_as_docs()`：

1. 再用同一正则抽关键词，逐词 `CONTAINS` 查询 Neo4j，并按 ID 去重。
2. 对前 5 个中心实体调用 `get_neighbors(max_depth=2)`，即无向遍历 1～2 跳；邻居再次按 ID 去重。
3. 收集带 `source_text_unit_id` 的实体 ID，最多保留 top_k 个作为来源提示。
4. `search_as_docs()` 把匹配实体和邻居依次转成 `ScoredDoc`，正文目前只有实体名，初始分数为 `1.0 - i*0.1`，metadata 保存实体总数和类型。
5. 三条子查询的结果汇总后按文档 ID保留第一次出现的结果，第一次通常也代表更靠前的排名。

关系入图后，Neo4j 的 1～2 跳遍历能够返回 `active/downgraded` 的真实邻接节点与关系；归档和软删除数据不会进入检索。还有一个实现细节是 workspace_id 为空时查询不会加租户过滤；正常 API 必须保证上游传入，不能依赖 Store 自动推断。

#### 3. PGVector 语义检索

向量路同样只处理前 3 条子查询，而且是逐条串行执行。`EntityEmbedder.embed_text()` 先调用 Gateway Embedding；API 失败再用本地 SentenceTransformer；全失败得到零向量。Pipeline 用 `not any(embedding)` 检测全零向量并跳过本次查询，避免拿零向量去做无意义排序。

有效向量进入 `similarity_search(table="text_unit_embeddings")`。Store 只允许三张白名单表，避免调用方把任意表名拼进 SQL；查询使用 pgvector 的余弦距离运算符 `<=>`，把相似度计算为 `1 - distance`，按降序取 top_k。SQL 条件 `(:workspace_id = '' OR workspace_id = :workspace_id)` 表示 workspace 非空时隔离，空字符串时会查询全表。返回的 `ScoredDoc` 正文是原 Chunk 文本，metadata 带 document_id 和表名。单条 Embedding 或 SQL 异常会被捕获并跳过，其他子查询与图检索仍可继续。

#### 4. Global 宏观检索

Global 路先拉取 workspace 下全部实体，按 `entity.type` 分组，再按每组实体数量降序保留前 5 种类型；每种类型最多展示前 10 个名称。拼好的实体文本截到 4000 字符，与当前 query 一起交给 Gateway，总结组件、技术栈、关系、架构模式和约束。模型异常时不返回空，而是退化成“查询 + 前 1000 字符实体列表”。没有任何实体时返回固定说明。

当前 Pipeline 每轮先调用一次 `global_search.search()` 保存 `global_result`，随后 `search_as_docs()` 内部又调用一次 `search()` 包装成 `ScoredDoc(id="global_summary", score=1.0)`，因此同一轮可能发生两次相同的 Global LLM 总结。语义缓存可能吸收第二次调用，但从代码结构看仍存在重复调用入口。它也不是社区检测式 GraphRAG，只是实体按类型聚合后的宏观摘要。

#### 5. RRF、反思循环和最终压缩

Local、Vector、Global 中至少两路非空时进入 RRF。对每一路中排名从 0 开始的文档累加 `1/(60+rank+1)`，再除以非空结果列表数量并降序排列；同一文档出现在多路会得到更高分。如果只有一路结果，Pipeline 直接保留该路原始分数，不经过 RRF。

反思上限 `max_reflection_rounds=2`，循环实际最多执行 3 轮检索：前两轮允许 Judge，最后一轮直接接受当前结果。Judge 只把前 5 个结果、每个最多 200 字符和三位小数分数交给模型，要求 JSON 返回 accept 或 refine。无结果时不调用模型，直接返回 refine，但 refined_query 仍是原 query；调用异常或 JSON 解析失败时默认 accept。refine 后把 sub_queries 重置为 `[refined_query]`，下一轮不再保留最初的多查询扩展。

最终 `ReRanker` 延迟加载 `BAAI/bge-reranker-v2-m3` 和 tokenizer，把每个候选构造成 `(query, doc.text[:512])`，批量 padding/truncation 到 512 Token，在 `torch.no_grad()` 下读取 logits 并排序取 top_k。模型加载失败则把 query 和正文按空格切词，用“原分数 70% + 词集合覆盖率 30%”重排；这种 fallback 对没有空格的中文效果有限。该本地模型是同步执行，运行在异步检索方法里时可能占用事件循环线程。

`Compressor` 按排序顺序装入最多 4000 个估算 Token：中文字符按 1.5、其他字符按 0.25 估算；完整文档放不下时，如果剩余预算超过 20，就按每 Token 约 2 字符截断最后一条并加省略号，然后停止。最终 `RetrievalContext` 保存原 query、实际 mode、压缩后的 results 和 Global summary；当前 `matched_entities`、`text_unit_evidence` 没有从中间结果回填，`total_tokens` 也仍是默认值。

Gateway 在 Rewriter、Embedding、Global Summary 和 Reflection 四处出现；Cross-encoder 是本地推理。当前前三类文本调用多使用通用 `task_type="default"`，仍经过护栏、限流、预算、缓存、熔断和 Failover，但还不能像 Analysis/Planning 一样按细粒度知识任务独立路由和计费。

### 当前实现边界

- QueryEnricher 生成了 `enriched_query` 和实体 ID，但主检索循环目前主要继续使用原 query/sub_queries，增强结果没有充分消费。
- Global Search 是“按实体类型聚合后由 LLM 总结”，不是完整的社区发现、社区报告式 GraphRAG。
- Neo4j/PGVector/Embedding 任一路失败时会尽量保留其他路结果，是可用性优先的降级设计。

### 面试话术

> 检索采用图、向量和 Global 三路组合。多路结果用 RRF 按排名融合，避免不同分数体系难以比较。融合后再让 ReflectionJudge 判断是否覆盖问题，不足就改写查询重查，最后用 Cross-encoder 精排并压缩到上下文预算。反思和重排失败都可以降级，不阻塞主业务。

常见追问：

- __为什么不用加权平均而用 RRF？__ Neo4j、余弦相似度和 LLM Global 结果的原始分数含义不同；RRF 只依赖名次，不要求先校准分数尺度。
- __为什么检索后还要 Reflection？__ 初次召回可能主题接近但没回答问题，Judge 能判断覆盖度并生成更合适的查询；设置最大轮数防止无限自我检索。
- __为什么 Reflection 失败默认 accept？__ 它是增强步骤，不是正确性的唯一来源。默认 accept 能保留已有召回结果，避免 Judge 故障拖垮问答。
- __workspace 隔离在哪里做？__ Neo4j、PGVector 查询和语义缓存都应带 workspace；不能先跨租户召回再在应用层过滤，否则既有泄露风险又浪费召回名额。

关键文件：`app/knowledge_layer/pipeline.py`、`app/knowledge_layer/retrieval/*.py`、`app/knowledge_layer/vector_store.py`。

---

## 3.5 分析层链路（Analysis，11 节点）

### 链路解决什么问题

把非结构化 PRD 转换为后续 Planning 可以稳定消费的需求、约束、依赖、领域、质量和工作量信息。

### 真实节点顺序

```text
parse
  → lang_detect
  → requirement → constraint → dependency → domain
  → quality → effort → stakeholder → clarity
      （每个智能节点：PromptTemplate
       → GatewayChatModel(task_type=analysis)
       → 护栏/限流/路由/Failover
       → PydanticOutputParser
       → 写回 AnalysisState）
  → assemble
```

`parse` 负责把原始 PRD 规范化为可分析内容；`lang_detect` 识别语言并在需要时翻译；`requirement` 提取功能与非功能需求；`constraint` 识别技术、业务、时间和合规约束；`dependency` 分析需求之间的前置关系；`domain` 判断业务领域；`quality` 给需求质量打分；`effort` 估算工作量；`stakeholder` 识别角色与关注点；`clarity` 找出歧义和需要澄清的信息；最后 `assemble` 组装统一的 `AnalysisResultDetail`。

| 节点 | 主要输入 | 主要产出 | 下游用途 |
| --- | --- | --- | --- |
| parse / lang_detect | 原始 PRD | 规范文本、语言、必要时的译文 | 给后续节点统一语料 |
| requirement / constraint | 规范文本 + 知识上下文 | 功能/非功能需求、硬约束 | Planning 的技术选型和组件拆分依据 |
| dependency / domain | 需求列表 | 前置关系、业务领域 | 安排组件边界与实施顺序 |
| quality / clarity | PRD 与已抽取需求 | 质量分、歧义、澄清问题 | 低质量输入可转人工确认 |
| effort / stakeholder | 需求和约束 | 工作量、角色、关注点 | 工期、技能和验收规划 |
| assemble | 各节点结构化字段 | `AnalysisResultDetail` | 作为 AnalysisAdapter 的统一输出 |

`parse` 不调用模型，而是按行扫描 `prd_raw`，用 `^(#{1,6})\s+(.+)$` 识别 1～6 级 Markdown 标题。每个标题生成 `DocumentSection(title, level, content)`；stack 保存当前父章节，遇到同级或更高级标题时弹栈，再把新章节加入父节点的 `subsections`。非标题行追加到最近章节，文档第一个标题之前的正文因为没有 section 会被忽略。结果列表保留全部章节的原始顺序，章节对象内部同时保留嵌套关系。

`lang_detect` 只取 PRD 前 200 字符判断语言，Pydantic 解析失败时默认中文。检测为英文才调用 `node="translate"` 翻译 `prd_raw[:8000]` 并覆盖 state 中的原文，翻译失败则继续使用英文。由于 parse 已经先执行，`prd_sections` 仍来自翻译前文本，翻译后不会重新解析章节，这是当前节点顺序带来的状态差异。

各智能节点送入模型的内容和降级值如下：

| 节点 | 实际输入裁剪 | 写回字段 | 模型/解析失败时 |
| --- | --- | --- | --- |
| requirement | `prd_raw[:8000]` | `extracted_requirements` | 写空列表 |
| constraint | `prd_raw[:6000]` | `extracted_constraints` | 写空列表 |
| dependency | 每条需求的 ID 和前 100 字符描述 | `dependency_graph` | 写空 DependencyGraph；没有需求时不调用模型 |
| domain | `prd_raw[:3000]` | `domain_tags` | 使用 `domain_tags`，为空再取 primary_domain；异常写“通用” |
| quality | ID、优先级和前 100 字符描述 | `confidence` | 0～10 分除以 10；无需求为 0，异常为 0.5 |
| effort | ID、优先级、分类和前 120 字符描述 | 当前只参与更新 `confidence` | 无需求或异常保持原状态 |
| stakeholder | `prd_raw[:4000]` | `stakeholders` | 写空列表 |
| clarity | ID 和前 150 字符描述 | `clarity_issues` | 无需求或异常保持原状态 |

除了 parse 和 assemble，节点都采用 `ChatPromptTemplate → GatewayChatModel(task_type="analysis", layer="analysis", node=节点名) → PydanticOutputParser`。Gateway 处理安全、配额、路由与 Provider 故障；Pydantic 再把返回约束成 RequirementList、ConstraintList、DependencyResult 等领域模型。大多数节点捕获调用和解析异常后写默认值，所以图能继续运行，但“到达 assemble”不代表所有维度成功，应该结合空结果和 confidence 判断。

Effort 节点的 Prompt 声称使用 COCOMO II，并能解析 total_effort_days、complexity 和 breakdown，但当前 `AnalysisState` 没有对应字段，节点也没有保存这些结果；`EffortResult` 没有 confidence 字段，因此代码最终用默认 0.5 与已有 confidence 求平均。面试时应说“具备工作量估算调用，但结果尚未完整贯通最终 AnalysisResult”，不能说已经输出了完整 COCOMO 估算。

`assemble` 从当前 prd_raw 第一行去掉开头 `#` 得到 project_name，用前 200 字符去换行形成 summary，再组合 domain、requirements、constraints、dependency、confidence、stakeholders 和 clarity_issues。AnalysisAdapter 只把 analysis_result、requirements、constraints 回填主状态并把 progress 设为 0.25。Adapter 虽会按组织加载 requirement 节点的租户 Prompt 到 `system_prompt`，但当前各节点模板并未普遍读取该字段，定制 Prompt 还没有完整贯通。

除了纯解析和组装节点，主要智能节点采用：

```text
ChatPromptTemplate
  → GatewayChatModel
  → LLM Gateway
  → PydanticOutputParser
  → AnalysisState
```

Pydantic 结构化解析使下游不依赖自由文本猜字段；Gateway 则统一处理 Provider、护栏、限流、成本和 Failover。AnalysisAdapter 只向子图传 `prd_raw`、知识上下文及可能的租户 Prompt，子图完成后把分析结果、需求和约束写回主状态并更新进度为 0.25。

Analysis 图创建共享的 `GatewayChatModel(task_type="analysis", layer="analysis")`，各 LLM 节点通过 LangChain 的 `ChatPromptTemplate | GatewayChatModel | PydanticOutputParser` 组合调用。`task_type="analysis"` 让 Gateway 可以给分析任务配置“质量优先”的主模型和备用模型；`layer/node` 会进入指标和 Trace，用来定位到底是 constraint、dependency 还是 clarity 节点慢或贵。

一次节点调用可以这样讲：RequirementNode 先把 PRD、知识上下文和租户 Prompt 填入模板，Gateway 对完整 Prompt 做注入检查与 PII 脱敏，按 workspace 预留 RPM/TPM 和预算，再从 analysis 路由选主模型；失败则由熔断器和 Failover 换备用模型。返回后先过输出护栏，再由 Pydantic parser 转成需求对象并写入 `AnalysisState`。如果格式解析失败，应由节点错误处理或重试策略处理，Gateway 主要保证传输层和模型治理，不替业务层猜测缺失字段。

### 为什么拆成 11 个节点

一个大 Prompt 虽然代码少，但很难知道是需求提取、依赖分析还是质量评分出了问题。拆分后每个节点输入输出更稳定，可单独测试、替换模型、追踪耗时，也能在特定节点配置不同 Prompt。

代价是 LLM 调用次数增加，因此要依赖 Gateway 的缓存、低成本路由、预算和观测能力。

### 面试话术

> Analysis 层不是生成长文本，而是做结构化需求理解。它按解析、语言、需求、约束、依赖、领域、质量、工作量、干系人和澄清顺序执行，最终组装统一分析模型。节点通过 Pydantic parser 约束输出，通过 Gateway 统一调用模型，解决一个大 Prompt 难测试、难定位的问题。

常见追问：

- __为什么这些节点串行，不全部并行？__ dependency、quality、effort 等节点需要前面已经抽取的需求或约束；存在数据依赖的节点串行更稳，真正无依赖的部分才适合并行。
- __Gateway 输出护栏和 Pydantic parser 有什么区别？__ 护栏解决安全、空响应和通用格式问题；Pydantic 校验业务字段、枚举和嵌套结构。前者是平台治理，后者是领域契约。
- __某个节点失败会怎样？__ Gateway 先处理超时、熔断和 Provider 切换；仍失败时节点记录错误并由图的异常策略决定终止或降级，不能用一份自由文本假装结构化结果成功。
- __拆节点会不会太贵？__ 会增加调用次数，所以配合 task_type 路由、语义缓存、低成本模型和逐节点成本指标；拆分换来的是可定位、可测试和可单独重跑。

关键文件：`app/analysis_layer/agent_graph.py`、`app/analysis_layer/models.py`、`app/analysis_layer/nodes/*.py`、`app/orchestrator/adapters/analysis_adapter.py`。

---

## 3.6 规划层链路（Planning，14 节点）

### 链路解决什么问题

把“需求是什么”转成“系统应该怎么设计和落地”，输出架构模式、技术栈、组件、数据、API、部署、风险、工期和成本等规划结果。

### 真实节点顺序

```text
knowledge_augment
  → pattern_recommend → pattern_confirm
  → tech_stack_select → component_decompose
  → cost_estimator → timeline_planner → skill_gap_analyzer → risk_quantifier
  → data_arch_design → api_planning → deployment_planning
      （智能节点统一经 GatewayChatModel(task_type=planning)，
       结构化解析后逐步写入 PlanningState）
  → self_check（同样经 Gateway）
      ├─ 通过 → assemble
      └─ 不通过且 < 3 次 → pattern_recommend
  → assemble
```

`knowledge_augment` 把知识检索结果加入规划上下文；模式节点先推荐再确认架构风格；随后选择技术栈、拆分组件，并补齐成本、时间、人力技能和风险；最后设计数据结构、API 与部署方案。

| 阶段 | 节点 | 核心产出 |
| --- | --- | --- |
| 上下文增强 | knowledge_augment | 与需求相关的技术知识和历史上下文 |
| 架构收敛 | pattern_recommend、pattern_confirm | 候选模式、理由和最终架构模式 |
| 方案拆解 | tech_stack_select、component_decompose | 技术栈、组件边界和职责 |
| 可交付性估算 | cost、timeline、skill_gap、risk | 成本、工期、人员能力缺口和风险 |
| 详细设计 | data_arch、api、deployment | 数据模型、接口契约和部署拓扑 |
| 质量闭环 | self_check、assemble | 完整性判断和统一 PlanningResult |

`knowledge_augment` 不复用主图已经得到的 query，而是取 `analysis_result.project_name` 拼成“项目名 架构设计 技术栈”，新建 RetrievalPipeline，以 hybrid、top_k=5 再检索一次。异常时返回只有 query 的空 RetrievalContext。当前调用没有传 workspace_id，因此这次规划内二次检索缺少租户过滤；而且后面的规划 Prompt 没有读取 knowledge_context，所以“知识增强”目前完成了状态写入，但还没有真正影响架构推荐。

规划节点并非全部都用同一种输出方式：

| 节点 | 实际决策方式与输入 | 保存位置 / 失败行为 |
| --- | --- | --- |
| pattern_recommend | 只输入项目名、领域标签、需求数量，要求 2～3 个候选 | Pydantic 转成 PatternEval；异常为空列表 |
| pattern_confirm | 不调用 LLM，直接对 `match_score` 取 max | 无候选时固定选择“分层架构” |
| tech_stack_select | 输入项目、选定模式、领域，固定要求 backend/database/cache/MQ/frontend/testing/CI-CD/monitoring 八个维度 | 转成 TechChoiceDetail；异常为空列表 |
| component_decompose | 只取前 10 条需求，每条描述最多 100 字符 | 转成 service/module/library 组件；异常为空列表 |
| cost_estimator | 输入项目、组件数、技术栈名称 | 结构化生成低配/标准/高可用三档月成本，写 `node_outputs.cost_estimates`；异常写空对象 |
| timeline_planner | 输入项目和组件数 | 自由文本写 `node_outputs.timeline`；没有节点级 try/except |
| skill_gap_analyzer | 输入技术栈名称 | 无技术栈直接跳过，否则自由文本写 `skill_gaps`；没有节点级 try/except |
| risk_quantifier | 输入项目、技术栈和组件数 | 结构化保存 probability、impact、risk_score、mitigation；异常写空列表 |
| data_arch_design | 输入项目和前 5 个组件名 | 自由文本写 `data_arch`；没有节点级 try/except |
| api_planning | 输入项目和前 5 个组件名 | 自由文本写 `api_plan`；没有节点级 try/except |
| deployment_planning | 输入项目和架构模式 | 自由文本写 `deployment_plan`；没有节点级 try/except |

所有节点更新 `node_outputs` 时先复制原字典再增加自己的 key，避免无意覆盖前序结果。结构化节点使用 PydanticOutputParser，自由文本节点直接读取 AIMessage.content。后者一旦 Gateway 最终失败会让子图整体抛异常，因为 timeline、skill gap、data、API、deployment 没有本地 fallback；所以“Gateway 有 Failover”不等于 Planning 永远不会失败，只是先消化 Provider 层故障。

`self_check` 实际只把架构模式、技术栈名称和组件数量发给模型，并不检查 data_arch、api_plan、deployment_plan 的正文。返回的 passed/issues 写入 `node_outputs`，无论成功失败都将 `self_check_attempts + 1`；调用异常视为不通过。条件边在不足 3 次时回到 pattern_recommend，因此会重新执行其后的所有节点；达到 3 次强制 assemble。

`assemble` 只把 selected_pattern、tech_stack_choices、component_decomposition 和基于组件依赖拼出的 Mermaid 写入 `PlanningResultDetail`，其他成本、时间、风险、数据、API、部署文本统一塞进 metadata。Mermaid 中内部依赖写 `Cdep --> Ccurrent`，找不到的外部依赖写 `EXT[依赖名] -.-> Ccurrent`。

`self_check` 使用 LLM 检查架构模式、技术栈和组件结果是否完整。结果写入 `node_outputs.self_check_passed`，同时把 `self_check_attempts` 加一。不通过时回到 `pattern_recommend` 重新跑后半段；达到 3 次仍失败则记录 warning 并强制进入 assemble，保证图一定终止。

如果上一次 Generation 已经经过 Evaluation，PlanningAdapter 会把 `critical_issues`、`recommendations` 和 `overall_score` 写入 `evaluation_feedback`。但当前 Planning 节点没有读取该字段，因此代码层面的重规划仍可能产生与上一轮相同的 Prompt；要形成真正反馈闭环，需要 pattern/tech/component 等节点显式把 feedback 加入输入，并确保缓存 Key随 Prompt 一起变化。

主要规划节点各自使用 `GatewayChatModel(task_type="planning", layer="planning", node="具体节点")`。业务上仍是一条 Planning 链，Gateway 层却能通过 node 标签看到模式推荐、成本估算或 API 规划分别用了多少 Token、耗时多久。Planning 的 Prompt 通常比分类任务更长，Gateway 会用“输入估算 + max_tokens”提前占用 TPM，并在真实 usage 返回后校正，防止 14 个节点连续调用瞬间打满 Provider 配额。

`self_check` 也走 planning 路由。它不通过时回到 `pattern_recommend`，这意味着后半段会再次产生模型成本；语义缓存可复用完全相同或高度相似的调用，预算控制则防止循环无限放大成本。熔断发生时只切换本次节点的 Provider，PlanningState 和 LangGraph 节点位置不变，因此备用模型成功后可以继续执行，不需要整条规划从头开始。

### 为什么模式推荐后还要确认

推荐节点可以给出候选和理由，确认节点负责收敛成唯一架构选择。将“发散”和“决策”分开，更利于解释选择依据，也方便未来加入规则或人工选择。

### 当前实现边界

- 自检连续失败后强制组装保证终止性，但产物应视为降级结果，而不是等同于正常通过。
- 14 个节点多数线性执行，稳定但耗时较长；未来可把成本、时间、技能和部分风险分析并行化。

### 面试话术

> Planning 层把分析结果转成可实施方案。它先用知识增强和架构模式收敛方向，再完成技术栈、组件、成本、工期、风险、数据、API 和部署设计。末尾有自检循环，不通过就回到模式推荐重新规划，最多三次防止死循环；主图评测回退时还会注入上一轮反馈。

常见追问：

- __为什么先定架构模式再选技术栈？__ 模式决定组件关系、部署方式和数据流，技术栈是实现手段；先选框架再想架构容易让方案被熟悉技术绑架。
- __为什么自检回到 pattern_recommend，而不是只修最后一个字段？__ 自检失败可能说明总体模式与组件设计不一致，需要从架构决策重新推导；最多三次保证图可终止。
- __如何避免重规划得到完全相同的结果？__ PlanningAdapter 注入上一轮评测的 critical issues、recommendations 和分数；Prompt 必须明确要求针对反馈修改。相同调用还可能命中缓存，因此缓存 Key/Prompt 中要包含反馈。
- __14 个节点性能会不会差？__ 当前多数串行，优点是依赖清晰；成本、时间、技能和部分风险分析可在状态契约稳定后并行化，但并行时仍受 Gateway 的 workspace RPM/TPM 控制。

关键文件：`app/planning_layer/agent_graph.py`、`app/planning_layer/models.py`、`app/planning_layer/output_models.py`、`app/planning_layer/nodes/*.py`。

---

## 3.7 生成层链路（Generation，8 节点 + 并行）

### 链路解决什么问题

根据分析和规划结果生成完整 TSD，并通过章节并行减少长文档生成时间。

### 完整流程

```text
outline
  → fan_out_sections
      ├─ Send(section_writer, 章节 A) ─┐
      ├─ Send(section_writer, 章节 B) ─┼→ gateway.stream_complete
      └─ Send(section_writer, 章节 N) ─┘   (generation.section_writer)
             → 限流/预算/缓存/路由/Failover
             → 完整输出护栏通过后释放安全 chunk
  → merge_contents reducer 合并
  → diagram（复用 Planning 已生成的 Mermaid，不调用 LLM）
  → code_scaffold → consistency → revision
      （这三个节点通过 GatewayChatModel(task_type=generation)）
  → assemble
  → export
```

大纲节点先生成 `SectionOutline` 列表。扇出函数检查 `section_contents`，只为尚未生成的章节创建 `Send`，因此评测后重新生成时可以保留已有章节并增量续写。

每个 `SectionWriter` 只负责一个 `_section_target`，通过 `gateway.stream_complete(task_type="generation.section_writer")` 生成 Markdown。节点把模型 token 暂存，每累计约 200 字符发布一次 `generation.chunk`，同时发布章节开始和完成事件。

并行节点不能共同覆盖整个字典，否则 LangGraph 会出现并行状态冲突。这里每个 writer 只返回自己的 `{section_id: content}`，`GenerationState.section_contents` 使用 `merge_contents` reducer 做字典合并，完成 fan-in 后才进入 diagram。

后续节点分别生成 Mermaid 等图表、代码脚手架，检查章节与规划的一致性，根据问题修订，再组装统一文档并导出 Markdown、DOCX、PDF 等格式。GenerationAdapter 把 `generation_result`、章节内容和导出结果写回主状态，进度更新为 0.75。

| 节点 | 职责 | 并行/串行原因 |
| --- | --- | --- |
| outline | 根据 Analysis 和 Planning 生成章节目录 | 必须先完成，后续章节依赖它 |
| section_writer | 按章节目标生成 Markdown 正文 | 章节之间弱依赖，使用 Send 并行 |
| diagram / code_scaffold | 补架构图与代码骨架 | 依赖已合并的正文和规划结果 |
| consistency | 比较章节、架构、接口和规划是否冲突 | 需要看到完整草稿 |
| revision | 按一致性问题修订 | 只处理已发现问题，避免全量重写 |
| assemble / export | 组装统一结果并导出格式 | 纯收口步骤，不负责重新推理业务内容 |

`outline` 也不调用 LLM。它根据 `analysis_result.domain_tags` 是否包含“电商”选择 ecommerce 或 default YAML 模板，再把模板中的 id/title/level 转成 SectionOutline，并把每节 estimated_tokens 固定为 500。模板文件不存在或没有章节时退化为“项目背景、总体架构、模块详细设计”三节，估算分别为 300/500/800。虽然类注释写“14 节大纲”，真实数量取决于 YAML，应该以模板内容为准。

`fan_out_sections()` 遍历 outline，只为 `section_id` 不在已有 section_contents 中的章节创建 `Send("section_writer", {**state, "_section_target": section})`。如果全部章节已经存在，它发送一个指向 diagram 的 Send，直接跳过写作。每个 writer 都拿到一份状态快照，但只返回 `{"section_contents": {id: content}}`；`Annotated[..., merge_contents]` reducer 复制旧字典后 update 新字典，完成并行 fan-in。

SectionWriter 的 Prompt 实际只包含项目名、架构模式、章节标题、完整技术栈列表和组件职责列表，没有使用 SectionOutline.description/estimated_tokens，也没有读取 evaluation_feedback、system_prompt 或 claims_constraints。调用 `stream_complete()` 时没有显式 temperature/max_tokens/workspace_id，依赖 Gateway 默认路由或请求 ContextVar。开始前发布 `generation.section=generating`；安全 chunk 累积到至少 200 字符时发布一次 `generation.chunk`；结束后发送剩余 buffer 和 `generation.section=done`，再把所有 token join 成章节正文。EventBus 发布失败是否影响 writer 取决于 publish 实现，节点自身没有包裹事件异常。

后续节点的真实工作如下：

- `diagram` 只把 `planning_result.component_diagram` 复制到 `mermaid_diagrams["architecture"]`，不重新生成图。
- `code_scaffold` 把所有组件职责和技术栈名称交给模型，要求输出项目目录、数据模型、API 骨架和依赖注入；自由文本直接写入 `code_scaffold`，没有结构化校验或本地 fallback。
- `consistency` 每个章节只截前 500 字符，用 `=== section_id ===` 拼接后交给模型。只有响应严格为空或“通过”才算无问题，其他每个非空行都作为 issue。
- `revision` 每章只截前 1000 字符，用分隔线拼成一段，要求模型返回修复后的完整内容；结果并不覆盖原章节，而是新增 `section_contents["_revision_fix"]`。
- `assemble` 严格按 outline 中的 section_id 读取正文，因此 `_revision_fix` 不在大纲中，不会进入最终 content。它随后追加 code_scaffold；Mermaid 只保存在 GenerationResultDetail.mermaid_diagrams，不自动插进 Markdown 正文。
- `export` 用 Markdown 库开启 fenced_code/tables/codehilite/toc 生成 HTML；缺库时退化为 `<pre>`。PDF 优先 WeasyPrint，失败转 fpdf2，但 fpdf2 会剥 HTML 并把非 latin-1 字符替换，中文质量有限。DOCX 按行识别 Markdown 标题，其余每行生成普通段落。PDF/DOCX 字节以 base64 放进 State，Markdown/HTML 直接保存字符串。

GenerationAdapter 会保留上轮 section_contents，实现迭代续写，并注入 evaluation_feedback、组织 Prompt 和 Claim 约束字段；但当前生成节点没有消费这些字段。Claim 查询还有额外限制：Adapter 只在 planning_result 是 dict 且存在 summary 时构造 query，正常 PlanningResultDetail 通常是 Pydantic 对象，因此常得到空 query；调用 search_claims 时也没有把 workspace_id 传下去。面试时应把这些描述为“Adapter 已预留反馈/约束接口，节点消费尚未闭环”。

代码骨架、一致性检查和修订节点使用 `task_type="generation"`；章节正文使用更细的 `task_type="generation.section_writer"` 调用 `stream_complete()`。Outline、diagram、assemble、export 是确定性代码，不经过 Gateway。这样 Gateway 可以让普通生成和长章节生成使用不同 timeout、主模型或 fallback，同时把 `layer=generation`、具体 node 写进观测数据。

并行章节会同时进入 Gateway，但不是无控制地直接打 Provider：每个调用都先做 workspace 的 RPM/TPM 预留，超过容量就被限流；预算检查发现费用接近上限时可以降级模型；某个 Provider 连续失败后熔断，后续章节直接尝试备用链。语义缓存按 workspace、task_type、模型和护栏版本隔离，相同章节重跑可能命中缓存，而不同租户不会互相读取。

### 流式 Gateway 的安全取舍

当前 Gateway 会把某次 Provider 的流式 chunk 先隔离缓冲，完整输出经过内容安全护栏后再释放。如果主 Provider 中途失败，其半截输出不会和备用 Provider 结果拼接。这样安全性更强，但严格意义上不再是“模型一生成 token 前端立即看到”，而是“模型完成并通过护栏后按原 chunk 边界交付”。

这里还要区分两层“流式”：Gateway 层是模型 chunk 的安全释放；SSE 层是应用事件传输。SectionWriter 收到安全 chunk 后累计约 200 字符再发布 `generation.chunk`，所以前端看到的粒度还会比 Provider chunk 更粗。缓存命中时没有真实 Provider 流，Gateway 会把缓存内容作为可用结果交回，但仍受相同租户和策略版本约束。

### 面试话术

> 生成层的核心是 Send 并行和 reducer 合并。大纲出来后，每个章节作为独立任务并行生成，只返回自己的字典增量，由 merge_contents 合并，避免并行写共享状态冲突。已有章节会跳过，方便评测后的增量重生成。章节内容还通过 EventBus 推送 SSE，之后再完成图表、代码、一致性检查、修订和格式导出。

常见追问：

- __Send 和普通 asyncio.gather 有什么区别？__ Send 是 LangGraph 的动态扇出，分支结果仍进入图状态和 reducer，便于 checkpoint、追踪和后续 fan-in；不是在节点内部偷偷创建一组无状态协程。
- __为什么需要 reducer？__ 多个章节并行返回时都要更新 `section_contents`。如果直接覆盖同一字段会冲突，`merge_contents` 按 section_id 合并增量。
- __并行会不会把模型配额打爆？__ 每个分支仍经过 workspace RPM/TPM 预留；超过当前限额时 Gateway 会拒绝调用，预算接近阈值时还可以触发低成本模型降级。
- __为什么说是流式但首包仍可能慢？__ Provider chunk 先在 Gateway 缓冲，完整输出过后置护栏才释放；随后 SectionWriter 又按约 200 字符发布业务事件，这是安全流式而非原始 token 实时透传。
- __重生成为什么能跳过章节？__ fan-out 会检查已有 `section_contents`，只为缺失目标创建 Send；但若评测要求修改已有章节，还需要显式标记该章节无效或进入 revision，不能仅靠“已存在就跳过”。

关键文件：`app/generation_layer/agent_graph.py`、`app/generation_layer/models.py`、`app/generation_layer/nodes/section_writer.py`、`app/generation_layer/nodes/*.py`。

---

## 3.8 评测层链路（9 维并行 + 综合评分）

### 链路解决什么问题

把“文档生成完成”变成“文档达到质量门槛”，并把问题反馈给主图决定接受、重新规划、重新生成或人工介入。

### 完整流程

```text
EvaluationState
  → fan_out_evaluators
      ├─ PRD 覆盖率 / 一致性 / 技术可行性
      ├─ 架构质量 / 安全性 / 成本合理性
      └─ 可实施性 / 技术先进性 / 法律合规
          （9 个 Send 分支分别调用
           GatewayChatModel(task_type=evaluation, node=维度)，
           输出结构化 DimensionScore）
  → merge_scores reducer 合并 dimension_scores
  → scoring
      → Gateway(task_type=evaluation_scoring) 补 completeness 或缺失维度
      → 显式权重加权
      → 历史分数校准
      → evaluation_scores 落库
  → EvaluationReportDetail
  → 主图 IterationDecider
```

条件入口检查已有 `dimension_scores`，只为缺失维度创建 `Send`。九个评测节点可以并行调用 LLM，总耗时更接近最慢节点，而不是九个耗时相加；所有节点完成后才进入 scoring。

综合评分实际口径是“9 个并行维度 + completeness 补充维度”。Scoring 优先使用子节点分数，LLM 只补缺失项，并返回结论、P0 覆盖率、问题和建议。九个核心维度使用显式权重，其中 PRD 覆盖率和一致性各 20%，可行性和安全性各 15%，其余维度合计 30%；completeness 不参与当前显式加权。

| 评测维度 | 主要检查内容 | 常见回流方向 |
| --- | --- | --- |
| PRD 覆盖率 / completeness | 需求是否遗漏、关键章节是否缺失 | Generation 补写，严重遗漏时回 Analysis |
| 一致性 | 章节、接口、数据模型、技术栈是否互相冲突 | Generation 修订或 Planning 重做 |
| 可行性 / 可实施性 | 方案是否能开发、部署和运维 | Planning 调整技术与组件 |
| 架构质量 / 技术先进性 | 分层、扩展性、选型是否合理且不过度设计 | Planning 重新选型 |
| 安全 / 法律合规 | 权限、数据、依赖和合规风险 | 严重问题转人工，其他问题回规划/生成 |
| 成本合理性 | 资源与复杂度是否符合预期 | Planning 调整架构或部署方案 |

`fan_out_evaluators()` 先读取已有 dimension_scores，只为缺失 key 创建 Send；如果九项都已存在就直接 Send 到 scoring。这让 checkpoint 恢复或重评时可以复用已有维度。每个评测节点收到同一份 EvaluationState，只返回自己的 `{"dimension_scores": {...}}`，`merge_scores` 复制旧字典后 update，从而把并行增量合并。节点输出模型统一为 `ScoreResult(score, issues, verdict)`，但当前各节点最终只取 score，issues 和 verdict 没有汇入综合报告。

九个维度实际看到的数据比名称更重要：

| 维度 | 实际输入给 Judge 的数据 |
| --- | --- |
| prd_coverage | Analysis 中全部需求的 ID + 前 100 字符描述，以及最终 TSD 的前 2000 字符 |
| consistency | Planning 的架构模式、技术栈名称和组件名，不读取最终 TSD 正文 |
| feasibility | 技术栈名称和架构模式 |
| architecture_quality | 架构模式和组件名 |
| security | 技术栈名称和组件名 |
| cost | 技术栈名称和组件数量，没有读取 cost_estimates 金额 |
| implementability | Planning metadata 中 skill_gaps 和 timeline，各截前 1000 字符 |
| tech_advancement | 技术栈名称和架构模式 |
| legal_compliance | 只读取 Analysis 的 domain_tags |

每个节点通过 `GatewayChatModel(task_type="evaluation", node=维度名)` 和 Pydantic parser 取 0～10 分；任何调用或解析异常都写中性分 5.0，而不是缺失。这意味着 Scoring 很难区分“模型真的打了 5 分”和“评测失败后兜底 5 分”。另外，除 coverage 外多数维度主要评价 Planning 摘要，不直接阅读生成文档，安全和法律维度也没有解析代码依赖或许可证清单，因此它更像轻量方案评审，而不是完整静态安全/合规扫描。

Scoring 的执行步骤是：

1. 从并行节点收集九个分数，并把 completeness 加入 required_dims。
2. 从 PostgreSQL 读取最近 10 条 EvaluationScore；查询没有 workspace/rubric 条件。
3. 调用 `GatewayChatModel(task_type="evaluation_scoring", default_model="gpt-4o-mini")` 获取十维 JSON。
4. 九个已有维度优先使用子节点分数，LLM 主要补 completeness；仍缺失的字段填 5.0。
5. 只对九个核心维度加权：coverage/consistency 各 0.20，feasibility/security 各 0.15，architecture 0.10，其余四项各 0.05；completeness 不进总分。
6. 有历史时用 `(本次加权分 + 历史 overall 平均值) / 2` 校准，再将所有维度保留一位小数。
7. 保存 EvaluationScore 并构造 EvaluationReportDetail。

当前 SCORING_PROMPT 只包含评分规则，没有把本次 Analysis、Planning 或 Generation 内容插入 Prompt，所以它补出的 completeness、conclusion、issues 和 recommendations 缺少本次方案上下文。并行维度分仍参与加权，但综合文字结论可信度有限。JSON 搜索使用贪婪的 `\{.*\}`；没有匹配、JSON 失败或任意异常时返回默认空报告。

ScoreCalibrator 读取最近 10 条历史分数，有历史时将当前加权分和历史平均分各占一半，以缓解单次 Judge 分数漂移。数据库读取或保存失败会降级为无历史校准，不中断评测。

EvaluationAdapter 把报告写回主状态并令 `iteration_count += 1`。主图根据总分、维度分、严重问题和最大轮数决定下一条边。

九个并行评测节点使用 `GatewayChatModel(task_type="evaluation", layer="evaluation", node="具体维度")`，综合 Scoring 补分使用 `task_type="evaluation_scoring"`。把维度节点分开后，Gateway 指标能看出哪个 Judge 最慢、最贵或失败最多；还可以把九维评测路由到速度/成本更均衡的模型，把最终综合判断交给更稳定的模型。

九路并发同样受 workspace RPM/TPM 控制，避免并行优化演变成 Provider 突发流量。某一维失败时，其他维度结果仍由 reducer 合并，Scoring 再补缺失项；Provider 故障则先在 Gateway 内 Failover。也就是说有两层容错：Gateway 解决“这次模型调用能否完成”，Scoring 解决“某个评测维度最终仍缺失时怎样形成报告”。输出护栏保证 Judge 的内容安全，Pydantic/评分模型负责验证分数字段和结构，两者职责不同。

### 当前实现边界

- 历史校准目前读取全局最近记录，Scoring 落库时传入的 workspace_id/task_id 为空，租户级校准还没有闭环。
- 各评测节点和 Scoring Prompt 使用 0～10 分，而主图 IterationDecider 的阈值是 70/85，当前量纲没有统一；面试时应将“85 分通过”作为设计目标说明，并指出实现上需要统一换算为百分制或把阈值改为 7/8.5。
- 达到最大迭代次数后当前策略是强制接受；生产系统更稳妥的做法是标记 degraded 并转人工。
- LLM-as-Judge 仍有自评偏差，需要稳定 rubric、固定温度、人工抽样和真实数据集校验。

### 面试话术

> 评测层用 Send 并行跑九个维度，每个节点只返回自己的 score，由 reducer 合并。Scoring 优先信任专门节点的分数，只让 LLM 补缺失维度，再按固定权重汇总并参考历史分数校准。报告回到主图后决定接受、重规划、重生成或人工介入，从而形成生成—评测—改进闭环。

常见追问：

- __为什么评测要并行？__ 九个维度主要读取同一份 PRD、规划和 TSD，彼此没有前置依赖；并行后耗时接近最慢维度，而不是九次调用相加。
- __一个维度失败会让整次评测失败吗？__ Gateway 先在该调用内 Failover；仍缺失时其他维度照常合并，Scoring 尝试补齐。若关键维度无法得到可信分数，应标记降级而非伪造满分。
- __历史校准为什么有用？__ LLM Judge 单次分数会漂移，和近期均值混合能降低抖动；但必须按 workspace、任务类型或 rubric 版本隔离，当前全局历史口径还不完整。
- __怎么避免模型自己生成、自己打高分？__ 使用明确 rubric、低温度、不同评测模型或 Provider、固定回归数据集和人工抽样；当前实现主要完成多维 Judge 与历史校准，不应夸大为完全客观。
- __0～10 与 70/85 阈值怎么解释？__ 这是当前实现的量纲缺口，应该统一乘 10 或把阈值改为 7/8.5；面试中应主动指出，而不是声称闭环已经正确。

关键文件：`app/evaluation/agent_graph.py`、`app/evaluation/scoring.py`、`app/evaluation/score_calibrator.py`、`app/evaluation/score_history.py`、`app/evaluation/nodes/*.py`。

---

## 3.9 人工审核与断点恢复链路

### 链路解决什么问题

在需求理解和架构规划两个高影响节点让人确认，并让长任务暂停后无需从头重跑。

### 完整流程

```text
Analysis 或 Planning 完成
  → needs_review(state)
      ├─ admin / auto_approve → 跳过审核
      └─ 默认 → HumanReviewNode
  → 构造 review_context
  → interrupt(review_context)
  → Checkpointer 保存 thread_id 对应状态
  → astream 暂停返回
  → TaskManager 标记 paused
  → EventBus 发布 task.review_required
  → 用户 POST /api/v1/review/{task_id}/{stage}
  → TaskManager 找到原 thread_id
  → Command(resume={decision, comment})
  → interrupt() 返回 feedback
  → 从断点继续后续节点
  → 后续智能节点重新按 task_type 进入 Gateway
      （已完成节点不重复调用；未提交成功的节点按图语义重试）
```

Analysis 审核上下文包含分析结果以及需求、约束数量；Planning 审核上下文包含规划结果以及组件、技术选型数量。审核数据放在 interrupt payload 中，调用方可以直接展示，不需要再次查询并拼接状态。

生产启动优先创建 PostgreSQL Checkpointer；失败时降级到 MemorySaver。PostgreSQL 支持进程重启后的状态恢复，MemorySaver 只适合单进程开发。TaskManager 还把任务索引写入数据库，使暂停任务重启后可以重新挂载 orchestrator。

`Command(resume=...)` 和重新 `ainvoke(initial_state)` 不同：前者是给上次 interrupt 的返回值，后者会被当作一次新的图执行，可能重复知识检索和模型调用。

`needs_review()` 的判断很简单：TenantContext.settings 中 `auto_approve=true`，或者 user_role 等于 admin，就返回 skip_review；其他角色默认进入审核。Analysis 的 interrupt payload 包含 analysis_result、需求数和约束数，Planning payload 包含 planning_result、组件数和技术选型数。payload 由 checkpointer 和图状态一起保存，前端收到 review_required 后可以直接渲染审核内容。

审核 API 的 `decision` 通过正则限制为 approved/needs_changes，stage 只允许 analysis/planning。TaskManager 先在内存字典找任务；进程重启导致内存未命中时，从持久化 task store 加载记录并重新挂载全局 orchestrator。只有任务状态正好为 paused 才能恢复，然后先写 resuming，异步启动 `_resume_task()`，用原 thread_id 调用 `astream(Command(resume={decision, comment}), config)`。

恢复过程中再次遍历 step_state 并发送进度；如果又遇到下一处 interrupt，任务会再次变成 paused。Checkpoint 保存的是 LangGraph channel values、节点位置和 interrupt 数据，不保存数据库连接、EventBus、Gateway 客户端等运行时对象，后者由恢复进程重新注入。PostgreSQL Checkpointer 可以跨进程恢复，MemorySaver 只能在当前进程内生效。

当前接口只验证“用户已登录”，没有在 pending 列表或 submit_review 中按 workspace、任务创建者、审核角色过滤；传入的 stage 也没有和任务真实 interrupt_stage 比较。HumanReviewNode 收到 needs_changes 后只把 status 设回 paused、error_message 写入评论，但主图从 analysis_human_review 固定连 planning、从 planning_human_review 固定连 generation，因此恢复后依然向后执行。这些都是面试中应明确的权限与返工闭环边界。

人工审核节点本身不调用 LLM，Gateway 客户端也不会被序列化进 checkpoint；checkpoint 保存的是可序列化业务状态、当前节点位置和 interrupt 信息。审核通过后，下一个 Analysis/Planning/Generation 节点再正常进入 Gateway。如果审核前的模型调用已经完成，恢复时不会重复扣费；如果某个模型节点尚未成功提交状态，则按图的重试语义重新执行，并重新经过 Gateway 的缓存、限流和 Failover。

异步任务创建时会复制当前 `ContextVar`，所以 HTTP 入口设置的 Provider、模型、timeout 和 Token 覆盖可以传给后台节点。恢复发生在另一个请求甚至另一个进程时，则应以持久化任务配置和 Gateway 路由配置为准，不能只依赖上一次请求内存中的上下文。

### 当前实现边界

- `needs_changes` 会把状态标为 paused 并记录意见，但主图审核节点后的边仍直接指向下一阶段，没有根据拒绝意见自动回到 Analysis/Planning 重做，反馈闭环需要继续完善。
- 审核接口验证了登录状态和 stage，但任务级 workspace/用户归属校验还应进一步加强。

### 面试话术

> 人工审核使用 LangGraph interrupt，不是自己轮询阻塞线程。图把状态写入 checkpointer 后暂停，TaskManager 将业务状态改成 paused 并推送 SSE。用户提交审核后，用同一个 thread_id 和 Command(resume) 恢复，LangGraph 从断点继续，因此不会重跑已经完成的昂贵节点。

常见追问：

- __暂停时占用线程或协程吗？__ 不占用等待线程。`interrupt` 把状态交给 checkpointer 后结束当前执行，恢复请求到来时再启动后续运行。
- __task_id 和 thread_id 为什么不能合并？__ task_id 面向 API、数据库和事件订阅；thread_id 面向 LangGraph checkpoint。分开后业务任务标识不受图执行实现影响。
- __进程重启后还能恢复吗？__ PostgreSQL Checkpointer 可以；降级使用 MemorySaver 时状态只在当前进程内，重启会丢失。
- __审核拒绝会自动返工吗？__ 当前 `needs_changes` 会记录意见和暂停状态，但审核节点后的条件边尚未完整回到 Analysis/Planning，属于已识别的实现边界。

关键文件：`app/orchestrator/human_review.py`、`app/orchestrator/routing.py`、`app/api/routes/review.py`、`app/task_manager.py`、`app/orchestrator/main_graph.py`。

---

## 3.10 会话记忆链路

### 链路解决什么问题

让新请求能参考同一 session 的历史决策，同时控制长会话上下文长度，并在结束后保存用户输入、AI 输出和摘要。

### 完整流程

```text
请求携带 session_id
  → 优先读取 state._history_messages
  → 没有则从 PostgreSQL 读取最近 50 条消息
  → MemoryRetriever hybrid 排序
      ├─ recency：24 小时指数衰减
      ├─ relevance：可选 gateway.embed 向量，否则关键词重叠
      └─ importance：可选 Gateway 判断，否则默认 0.5
  → 0.3×recency + 0.4×relevance + 0.3×importance
  → top_k 记忆写入 retrieved_memories
  → 注入 chat/QA 或复杂生成上下文
  → 主任务完成
  → ContextCompressor
      ├─ summarize：优先经 Gateway 总结旧消息
      ├─ rolling
      └─ truncate
  → SaveSessionNode 写 sessions/session_messages
```

复杂生成在知识检索前经过 `retrieve_memory`；chat 和 knowledge_qa 节点也可以通过共享的 `build_memory_context` 获取相关历史。数据库读取失败时降级为空记忆，不影响当前请求。

压缩器默认上下文上限 128K Token，并为最新内容预留 32K。超过上限后优先让 LLM 总结旧消息；无法总结时保留最近消息；仍不满足时截断。最新消息作为保护区，避免用户当前需求被旧摘要挤掉。

`SaveSessionNode` 会解析或创建 session，保存本次用户输入及 chat_response/generation_result，更新摘要和状态，并发布 `task.saved`。保存失败只记录告警，不把已经生成成功的任务改成失败。

历史加载优先读取 State 中的 `_history_messages`，只要非空就不查数据库；否则要求存在 session_id，并调用 `SessionRepository.get_messages(page=1, page_size=50)`。加载结果只有 role、content、timestamp，随后回写 `_history_messages` 避免同一次图执行重复查库。数据库异常返回空列表，不阻塞当前请求。

MemoryRetriever 会为每条历史消息构造 MemoryItem。timestamp 支持 datetime 或 ISO 字符串，解析失败按当前时间处理；recency 使用 `exp(-hours_ago/24)`，所以 24 小时后的分数约为 0.368，代码注释称“半衰期”并不严格。关键词 relevance 将 query/content 小写后按空格切成集合，交集数除以 query 词数，对连续中文句子的效果有限。importance 在没有 Gateway 时固定为 0.5；注入 Gateway 时会逐条截前 300 字符，让模型返回 0～1 数字并夹紧范围。hybrid 最终为 0.3×recency + 0.4×relevance + 0.3×importance，再排序取 top_k。

向量 relevance 的实现也要讲准确：只有 MemoryRetriever 注入 vector_store 才执行；它只对 query 做 Embedding，然后调用该 Store 的 similarity_search(top_k=1)，并把第一条命中的分数当作当前消息相关度，并没有直接对每条历史消息内容生成向量。因此它目前不是完整的“逐消息向量相似度”。默认依赖注入创建 `MemoryRetriever()`，既没有 vector_store 也没有 gateway，所以主图实际主要使用时间分、空格关键词覆盖和固定重要度。

ContextCompressor 先估算全部消息 Token，未超过 128000 就原样返回。超过后从最新消息向前累计最多 32000 Token作为保护区，旧消息依次尝试 summarize、rolling、truncate。Summarize 最多取前 20 条旧消息、每条 500 字符，调用 `memory_compress`；但默认注入的 `ContextCompressor()` 没有 Gateway，所以第一策略会原样返回并继续尝试 rolling。Rolling 从新到旧保留完整消息直到预算不足；truncate 则不断把过长文本对半截短。三种策略仍不能满足时只返回保护区。

SaveSession 自行从 connection_manager 创建数据库会话，不依赖 checkpoint 内的 Runtime。不存在 session 时，用 PRD 前 50 字符作标题、按 intent 决定 session_type，并把 task_id 当作 session 的 thread_id；随后用户消息最多保存 20000 字符、AI 内容最多 50000 字符。compressed_context 存在时把每条前 200 字符拼成最多 1000 字符摘要，否则使用回答/结果摘要；更新 session 状态后 commit，再尽力发布 task.saved。任何持久化异常只记 warning，最后仍注销 runtime 并返回原 State。

记忆检索的相关性可以走 Embedding，重要度判断和超长历史摘要可以走文本模型，因此设计上都应经过 Gateway：Embedding 使用 embedding 路由，摘要/重要度使用成本较低的记忆类任务路由，并继承 workspace 的限流、预算和缓存。这样记忆增强不会悄悄形成一套无法统计的模型费用。

当前默认 `MemoryRetriever` 没有注入 vector_store 和 Gateway，所以它通常退化为关键词相关性、默认重要度和时间分；这意味着主链可用，但“语义记忆”和“LLM 重要度”并非默认完整开启。面试中应按这个边界描述，不要说每次会话都一定调用了 Gateway 做语义记忆。

### 会话记忆和 Checkpoint 的区别

- 会话记忆面向模型语义：保存用户说过什么、系统做过什么。
- Checkpoint 面向程序执行：保存图跑到哪个节点、每个状态字段是什么。
- `session_id` 用于对话连续性，`thread_id` 用于执行连续性，不能互相替代。

### 当前实现边界

- 默认注入的 MemoryRetriever 没有 vector_store 和 LLM Gateway，因此 hybrid 策略通常退化为关键词相关性 + 默认重要度 + 时间分。
- SaveSession 创建会话时用 task_id 作为 thread_id 保存，和 TaskManager 单独生成的 LangGraph thread_id 口径并不完全一致。

### 面试话术

> 记忆链路先从数据库恢复最近消息，再按时效、相关性和重要度融合排序，只把最相关内容交给模型；结束时对超长上下文做摘要、滚动窗口或截断，再持久化。记忆解决语义连续性，checkpoint 解决程序断点恢复，这是两套不同机制。

常见追问：

- __为什么只取最近 50 条后再排序？__ 先用数据库窗口控制候选规模，再做混合排序，避免长会话每次对全部历史做 Embedding 或 LLM 判断。
- __三个分数为什么这样配？__ relevance 权重最高保证回答当前问题，recency 防止旧信息压过新决策，importance 保留关键约束；权重是工程初值，需要用真实会话评测调优。
- __摘要会不会丢信息？__ 会，所以最新消息设为保护区，旧内容才进入 summarize；摘要失败再降级 rolling/truncate。关键业务决策更适合额外结构化保存，而不是只依赖自然语言摘要。
- __当前真的用了向量记忆吗？__ 默认依赖注入没有 vector_store 和 Gateway，通常会降级到关键词、时间分和默认重要度，面试时必须说明这是可扩展设计与当前装配之间的差距。

关键文件：`app/orchestrator/nodes/retrieve_memory.py`、`app/orchestrator/nodes/memory_context.py`、`app/orchestrator/nodes/compress_memory.py`、`app/orchestrator/nodes/save_session.py`、`app/session_history/*.py`。

---

## 3.11 SSE 流式链路

### 链路解决什么问题

长任务不能让用户只看到转圈。SSE 用一条单向 HTTP 长连接推送任务进度、章节内容、审核请求、错误和心跳。

### 完整流程

```text
客户端以 stream=true 调用 /interact
  → FastAPI 返回 StreamingResponse(text/event-stream)
  → complex_generation 创建 task_id
  → 客户端订阅 channel = task:{task_id}
  → 生成节点调用 Gateway.stream_complete
      → Provider chunk 暂存
      → 完整输出通过后置护栏
      → SectionWriter 每累计约 200 字符发布 generation.chunk
  → TaskManager/其他节点发布 progress/review/done/error
  → EventBus 为每个订阅者维护独立 asyncio.Queue
  → subscribe_task_events 从 Queue 取事件
  → SseEvent 序列化为 data: JSON\n\n
  → 30 秒无业务事件则发送 keepalive
  → done/error 结束，或客户端断开触发取消订阅
```

EventBus 是进程内 Pub/Sub。一个 channel 可以有多个订阅者，每个订阅者有独立队列，互不抢消息。Queue 的 `maxsize=128`，慢消费者积压满后丢弃新事件而不是阻塞生成任务，避免回压拖垮主链。

事件统一包含 `type`、`payload` 和 UTC timestamp。主要事件包括任务创建/进度/状态/审核/保存、对话与问答 chunk、章节状态、生成 chunk、keepalive、done 和 error。

HTTP 响应设置 `Cache-Control: no-cache`、`Connection: keep-alive` 和 `X-Accel-Buffering: no`，防止 Nginx 缓冲破坏实时推送。30 秒心跳用于保持中间代理连接并让客户端知道服务仍存活。

`SseEvent` 是包含 type、payload、timestamp 的 dataclass；timestamp 缺失时使用 UTC ISO 时间。序列化时没有使用 SSE 原生 `event:` 字段，而是统一输出一行 `data: {JSON}\n\n`，事件类型放在 JSON 的 type 字段中，因此前端需要解析 data 后再按 type 分派。error payload 固定含 message/code，done 含 task_id/result_summary。

EventBus 的 `_channels` 是 `channel → set[Queue]`。subscribe 在锁内创建 maxsize=128 的独立队列并加入集合；publish 只在锁内复制订阅者列表，随后逐个 `put_nowait()`，某个队列满只丢该订阅者的当前事件，不影响其他订阅者和生产任务；unsubscribe 会删除队列，并在集合为空时清理 channel。它没有历史缓冲，订阅前发布的事件无法补发。

`subscribe_task_events()` 先直接 yield created/snapshot 等 initial_events，然后才调用 EventBus.subscribe；这个顺序保证初始事件最先展示，但 initial event 输出到真正注册队列之间存在很小竞态窗口，后台任务如果极快发布事件，可能丢失。订阅后用 `asyncio.wait_for(queue.get(), timeout=30)` 等待，超时就生成 keepalive；收到 done/error 退出；浏览器断开导致 CancelledError 时静默结束，并在 finally 保证 unsubscribe。

普通 chat/QA 流并不经过 EventBus，而是路由内部直接把 Gateway chunk yield 为 qna.chunk；复杂生成才通过 `task:{task_id}` 频道汇聚 TaskManager 和 SectionWriter 事件。因此横向扩容时不仅要把 EventBus 换成 Redis/Kafka，还要考虑任务创建后订阅的竞态、事件序号、重连游标和最终任务快照查询。

Gateway 决定“模型内容什么时候安全可见”，EventBus/SSE 决定“业务事件怎样送到客户端”。如果主 Provider 流到一半失败，Gateway 丢弃这次暂存并切备用 Provider，前端不会收到两家模型拼接的答案；如果 EventBus 队列已满，丢失的是应用推送事件，不影响 Gateway 已完成的模型调用和任务最终状态。排查问题时因此要先判断是 Provider/Gateway 失败，还是 SSE 传输丢事件。

### 为什么使用 SSE 而不是 WebSocket

这个场景主要是服务端向浏览器单向推送。SSE 复用 HTTP、协议简单、文本事件易调试；审核提交等客户端动作继续走普通 POST 即可，不需要为双向连接承担 WebSocket 的连接管理成本。

### 当前实现边界

- EventBus 是单进程内存实现，多 API 实例之间不能共享事件；生产横向扩容需要 Redis Streams/PubSub、Kafka 等外部总线。
- 队列满时事件会丢弃，目前没有 sequence ID 和断线补偿，客户端重连后应主动查询任务快照。
- 浏览器原生 EventSource 只能方便地发 GET，而 `/interact` 是 POST；前端需要 `fetch + ReadableStream` 解析 SSE。

### 面试话术

> SSE 负责进度和内容可见性，EventBus 负责生产者和 HTTP 连接解耦。每个订阅者有独立、有限长度的 Queue，慢客户端不会阻塞 Agent；30 秒心跳维持连接，done/error 负责终止。因为业务主要是服务端单向推送，所以 SSE 比 WebSocket 更简单。

常见追问：

- __为什么不用 WebSocket？__ 当前交互主要是服务端推事件，用户审核可另走 POST；SSE 基于 HTTP、代理兼容和调试成本更低。
- __慢客户端怎么办？__ 每个订阅者队列最多 128 条，满后丢新事件而不阻塞生产者；最终结果应从任务查询接口补偿，而不能把 SSE 当可靠消息队列。
- __多实例部署有什么问题？__ EventBus 是进程内内存结构，发布者和订阅连接落到不同实例就收不到事件；需换 Redis Streams/PubSub 或 Kafka，并设计 sequence ID 和重放。
- __模型流和 SSE 流是一回事吗？__ 不是。Gateway 先把 Provider 输出变成安全 chunk，业务节点再封装为事件，EventBus 最后通过 SSE 传输，三层失败点不同。

关键文件：`app/streaming/event_bus.py`、`app/streaming/sse.py`、`app/streaming/models.py`、`app/api/routes/interact.py`、`app/generation_layer/nodes/section_writer.py`。

---

## 3.12 文档上传与多格式入图链路

### 链路解决什么问题

把用户上传的文件可靠地保存下来，并异步转换为 3.3 的知识索引，避免解析和 LLM 提取阻塞上传接口。

### 完整流程

```text
POST /api/v1/documents/upload
  → JWT 与 workspace 上下文
  → UploadFile.read()
  → 校验扩展名与 50MB 上限
  → SHA-256(content)
  → workspace 内按 hash 查重
      ├─ 已存在 → 返回原记录，deduplicated=true
      └─ 不存在 → 继续
  → MinIO 保存原始字节
  → PostgreSQL 创建 uploaded_documents
  → processing_status=pending
  → index_document_to_kg.delay(document_id)
  → Celery Worker 下载 MinIO 文件
  → processing
  → KnowledgeGraphBuilder.build_from_bytes
      → Loader 提取正文 + 独立/内嵌图片
      → gateway.analyze_vision(vision) 做 OCR 与图片语义描述
      → 合并带来源的 OCR 文本 → Chunker
      → Gateway 完成实体、关系与 Claims 抽取
      → Gateway Embedding
      → Neo4j + PGVector 落库
  → indexed / failed
```

允许类型包括 md、pdf、docx、txt、csv、tsv、png、jpg/jpeg。去重 Key 是文件字节 SHA-256，并结合 workspace 查询，因此同一租户重复上传不重复存储，不同租户仍保持数据边界。

MinIO 路径包含 workspace、年月、文件哈希和扩展名。MinIO Python 客户端是同步 API，上传操作通过 `asyncio.to_thread` 放入线程池，避免阻塞 FastAPI 事件循环。

Celery 任务使用 Redis 作为 broker/result backend，入图失败最多重试 3 次、间隔 60 秒。任务执行时从 PostgreSQL 获取元数据、从 MinIO 下载文件，状态先改为 processing；成功改为 indexed，失败写 failed 和 processing_error。

上传接口不等待入图完成，所以前端应根据 `processing_status` 展示“处理中/可检索/失败”，而不是上传成功就立即假设知识检索可用。

上传路由先从 `request.scope` 读取 workspace；缺失直接返回 400。随后 `await UploadFile.read()` 一次性把整个文件读进内存，再在 Service 中用字节长度检查 50MB，因此它不是流式落盘，大量并发接近上限的上传会形成明显内存压力。类型判断只看文件名最后一个扩展名的小写结果，不检查 magic bytes，也没有病毒扫描或压缩炸弹检测。

去重先对原始字节做 SHA-256，再用 `workspace_id + file_hash + is_deleted=false` 查 uploaded_documents。命中时直接返回旧 DocumentOut，不重新上传、不重新触发入图；这意味着旧记录若处于 failed，用户重复上传相同文件也只会拿到 failed 记录，需要显式 reindex。不同 workspace 使用相同文件仍会分别保存业务记录和对象路径。

MinIO bucket 固定为 `prd-docs`，对象 key 为 `prd-docs/{workspace}/{yyyy}/{mm}/{sha256}{ext}`。客户端和 bucket 被延迟获取；bucket_exists、make_bucket、put_object 这三个同步调用通过 `asyncio.to_thread()` 执行。上传流来自内存 BytesIO，content-type 由扩展名映射。Storage 返回 storage_path/file_hash/file_size，但没有把推断的 mime_type 放进返回字典，所以数据库中的 mime_type 当前通常为 None。

数据库记录通过 `db.add → flush → refresh` 创建，包含 workspace、user、原文件名、大小、类型、哈希、对象路径、session 和 tags。Service 随后更新 processing_status=pending 并调用 `.delay(document_id)`；repository 方法主要 flush，由 FastAPI 的会话生命周期负责最终事务处理。需要意识到 MinIO 上传和数据库写入不是一个事务：对象成功但 DB 失败会留下孤儿对象；DB 成功而 Celery 发布失败会留下长期 pending 记录。

Celery broker 和 result backend 都使用 REDIS_URL。Worker 是同步 Celery task，内部用 `asyncio.run()` 启动异步处理：按 document_id 查询 ORM 记录，缺记录或 storage_path 为空就返回 skipped；从 MinIO 下载字节后写 processing，调用 `build_from_bytes()`；成功写 indexed，异常写 failed/processing_error 后重新抛出，让 Celery 最多重试 3 次、默认间隔 60 秒。状态更新与入图库共用同一 async session 范围，但 Neo4j/PGVector 仍是外部独立提交，无法随文档状态一起回滚。

上传、哈希、MinIO 和数据库落库都不需要 LLM；真正进入 Gateway 的位置在 Celery 调用 `KnowledgeGraphBuilder` 之后。若文件含图片，先走 `vision` 路由完成 OCR；之后实体、关系、Claims 抽取和 Chunk/Entity/Claim Embedding 继续走各自路由。Celery 字节流、Markdown 文件和 URL 最终复用 `build_from_text()` 的同一核心步骤。Worker 内 OCR 同样受护栏、预计 TPM、预算、熔断和 Failover 治理，最终失败则由 Celery 最多重试 3 次。

需要注意两层重试边界：Gateway 的 Failover 是同一次抽取调用内切换 Provider；Celery 重试是整次文档入图任务在 60 秒后重跑。前者处理短时模型故障，后者处理数据库、对象存储或整个处理任务失败。语义缓存可以减少 Celery 重跑时相同 Prompt 的重复模型费用。

删除流程先尝试删 MinIO，再把数据库记录标记 `is_deleted=true/deleted_at=now`；即使 MinIO 删除失败，Service 仍继续软删数据库。详情、删除、预览和 reindex 路由按 document_id 查询时没有额外传 workspace 条件，当前主要依赖“用户已登录”，资源级租户归属校验还不完整。reindex 只更新 pending/error 字段，没有重新发布 Celery 任务。

### 当前实现边界

- Celery 不可用时上传仍然成功，但只记录告警并跳过入图，需要运维监控 pending 文档。
- `reindex()` 当前只把状态改回 pending，没有再次调用 `_trigger_kg_index`，重索引接口的实际任务触发还未闭环。
- 删除流程会删 MinIO 对象并软删除文档记录，但知识图谱和向量索引的级联清理需要单独确认。

### 面试话术

> 上传链路把原始文件存储和知识加工解耦。API 只做类型、大小、workspace 内哈希去重、MinIO 和 DB 落库，然后用 Celery 异步入图。processing_status 对外暴露处理状态，Celery 失败会重试，因此上传接口响应快，解析和 LLM 成本也不会占用 API worker。

常见追问：

- __为什么先存原文件再发 Celery？__ Worker 只需要 document_id 就能从数据库和 MinIO 重建输入；任务失败或服务重启后仍可重试，不依赖上传请求内存中的字节。
- __如何去重？__ 对原始字节计算 SHA-256，并在 workspace 内查询。相同内容跨租户不共用业务记录，避免数据归属混乱。
- __Gateway Failover 和 Celery retry 有什么区别？__ Failover 在单次 LLM 调用内切 Provider；Celery retry 在整次入图失败后重跑，包括存储、解析和数据库异常。
- __重复消费任务会不会重复入库？__ 当前依赖文档记录和底层 upsert/重建行为，生产上还应把 document_id、chunk_id、entity key 设计成稳定幂等键，并记录各阶段完成状态。
- __上传成功是否代表可检索？__ 不是。上传成功只代表原文件和记录已保存，必须等 `processing_status=indexed`。

关键文件：`app/api/routes/documents.py`、`app/document_management/service.py`、`app/document_management/storage.py`、`app/document_management/deduplication.py`、`app/batch/tasks.py`。

---

## 3.13 URL 文档分析与 SSRF 防护

### 链路解决什么问题

让用户直接提交公网 URL 做总结、入库或生成 TSD，同时阻止服务端被利用去访问 localhost、云元数据地址和内网服务。

### 完整流程

```text
/interact 携带 url
  → 强制判定 document_analysis
  → validate_url
      ├─ 长度 ≤ 4096
      ├─ 仅 http/https
      ├─ 必须有 hostname
      ├─ 拒绝 localhost
      ├─ IP 字面量不得是私网/环回/链路本地/保留/组播/未指定
      └─ DNS 解析的所有 IP 再执行同样检查
  → WebLoader 使用 30 秒超时抓取
  → 去 script/style/HTML 标签，提取标题和正文
  → 根据请求分流
      ├─ 普通分析：上传为 Markdown → 标记 file_type=url/source_url
      │              → gateway.complete/stream_complete(document_analysis)
      └─ generate=true：抓取文本创建复杂生成任务
                     → Analysis/Planning/Generation/Evaluation 各自经 Gateway
```

DNS 检查很重要，因为 URL 主机名表面上不是 `127.0.0.1`，但可能解析到 `10.x`、`172.16.x` 或 `169.254.169.254`。校验使用 `socket.getaddrinfo`，检查所有 A/AAAA 结果；DNS 是阻塞调用，所以通过 `asyncio.to_thread` 执行。

`validate_url()` 先拒绝空字符串和超过 4096 字符的输入，再用 `urllib.parse.urlparse()` 解析。scheme 转小写后只允许 http/https，hostname 必须存在；localhost、localhost.localdomain、ip6-localhost 直接拒绝。IP 字面量用 `ipaddress.ip_address()` 判断 private、loopback、link_local、reserved、multicast、unspecified 任一属性；域名则调用 `socket.getaddrinfo(hostname, None)` 并逐个检查所有返回地址，只要一个地址不安全就拒绝。函数返回原 URL，并没有进一步规范化 path、端口或用户信息。

`UrlDocumentService.fetch_content()` 用 `asyncio.to_thread(validate_url, url)` 避免 DNS 阻塞事件循环，再交给 WebLoader。WebLoader 创建 `httpx.AsyncClient(timeout=30, follow_redirects=True)`，使用固定 Prd2TsdBot User-Agent，并允许调用方 header 覆盖；`raise_for_status()` 把非 2xx 变为错误。返回结构同时保存原 HTML、content-type、status code、title、纯文本和简化 Markdown；timeout、HTTP 错误或其他异常先写进 result.error，再由 UrlDocumentService 转成 ValueError。

标题通过不区分大小写的 `<title>` 正则提取。纯文本处理先删除 script/style，尽量截取 body 内部，再删除全部标签并把连续空白压成单空格，最后硬截前 10000 字符。Markdown 转换会按 article/main/content/post/article/body 顺序选择第一个正文起点，再尝试寻找对应结束标签；随后用正则转换 h1～h4、p、br、li、粗体、斜体、链接、code 和 pre，删除残留标签并把三个以上换行压成两个。它不解析 DOM，也不解码复杂实体或执行 JavaScript，所以 SPA 页面、嵌套标签和格式不规范页面可能提取不准。

URL 入库前要求 workspace，正文不能为空且最大 20MB。页面标题或域名被转换为安全文件名，以 `.md` 形式复用普通文档上传、去重、MinIO 和异步入图链路；随后把数据库记录改成 `file_type=url` 并保存 `source_url` 供溯源。

入库时优先取 Markdown content，没有才用 text_content，编码为 UTF-8 后检查 20MB。文件名优先使用标题中“字母数字、连字符、下划线”组成的字符，最多 80 字符；标题清洗后为空就使用 URL netloc，最后加 `.md`。它调用普通 DocumentManagementService.upload，所以会执行 SHA-256 去重、MinIO 保存和 Celery 入图，随后再把数据库 file_type 改成 url 并写 source_url。若去重命中已有 Markdown 记录，这次 update 会把同一记录改成 url 类型，这是复用上传链带来的行为。

文档分析 Prompt 只取抓取文本前 12000 字符，拼接 source_label 和用户 instruction；同步模式使用 complete、默认最大输出 2048，流式模式使用 stream_complete。`generate=true` 目前只接受 URL，不接受 doc_id 一键生成；它复用已抓取正文创建 TaskManager 复杂任务，避免再抓一次页面。

SSRF 校验和网页抓取发生在 Gateway 之前，因为 Gateway 只治理模型调用，不能替代网络出口安全。正文抓取成功后，普通文档分析调用 `gateway.complete(task_type="document_analysis")`；流式分析调用同类 `stream_complete()`；`generate=true` 则把正文交给 3.2 主图，后续分别进入 analysis、planning、generation、evaluation 路由。若同时入库，还会异步复用 3.12/3.3 的抽取与 Embedding Gateway 链路。

因此完整安全边界是“URL 层阻止服务端访问危险地址，Gateway 输入护栏阻止恶意正文操纵模型，Gateway 输出护栏阻止不安全结果返回”。三层关注的问题不同，不能只做 Prompt 注入检测就声称解决了 SSRF。

### 当前实现边界

- WebLoader 开启 `follow_redirects=True`，但只在初始 URL 抓取前校验一次，没有逐跳校验重定向目标；攻击者可能用公网 URL 302 到内网地址。
- DNS 校验和真正建立连接之间存在时间差，当前没有把已验证 IP 绑定到连接，仍需考虑 DNS Rebinding/TOCTOU。
- HTML 正文提取是简单正则和标签清理，不是完整 Readability，对复杂网页、动态渲染和反爬页面效果有限。

### 面试话术

> URL 分析入口先做 SSRF 校验，只允许 HTTP/HTTPS，并对主机名解析出的全部 IP 拒绝私网、环回、链路本地和保留地址。抓取后校验内容大小，再复用文档上传链落库和入图。当前还需要补逐次重定向校验和连接阶段的 DNS 绑定，这是 SSRF 防护从基础版走向生产版的重点。

常见追问：

- __为什么校验域名后还要校验解析 IP？__ 攻击者可以使用一个看似公网的域名解析到 127.0.0.1、10.x 或云元数据地址；只做字符串黑名单不够。
- __为什么重定向还要逐跳校验？__ 初始公网地址可能返回 302 指向内网。如果 HTTP 客户端自动跟随而不重新校验，初次验证就被绕过。
- __DNS Rebinding 是什么？__ 校验时域名解析到公网 IP，真正连接时又解析到内网 IP；解决思路是绑定已验证 IP、限制重解析并校验证书/Host，而不只是重复调用 DNS。
- __Prompt Injection 能防 SSRF 吗？__ 不能。SSRF 是抓取阶段的网络安全问题；Prompt Injection 是正文进入模型后的指令安全问题，两层都要做。
- __为什么保存为 Markdown？__ 抓取结果已是清洗后的标题和正文，转为统一文本格式可以直接复用上传、去重、MinIO 和异步入图链路。

关键文件：`app/web_indexing/url_security.py`、`app/web_indexing/url_document.py`、`app/web_indexing/web_loader.py`、`app/api/routes/interact.py`、`tests/unit/test_url_security.py`。

---

## 3.14 认证授权与多租户链路

### 链路解决什么问题

确认请求是谁发起的、属于哪个组织和工作空间、拥有哪些权限，并让知识、预算、Prompt 和业务数据按租户隔离。

### 注册与登录流程

```text
注册
  → 邮箱查重
  → bcrypt 加盐哈希密码
  → 创建 User
  → 创建默认 Organization
  → 创建个人 Workspace
  → 创建 admin Role
  → 创建 TeamMember 关系
  → 签发 access_token + refresh_token

登录
  → 按邮箱查询 User
  → bcrypt.checkpw
  → 检查 active 状态
  → 读取最近加入的 workspace 和 role
  → 将 sub/org_id/ws_id/permissions 写入 access token

后续业务请求
  → AuthMiddleware 验签并写 request.scope
  → WorkspaceContextMiddleware 确定 workspace_id
  → 路由依赖校验 permission / 资源归属
  → 业务查询按 workspace_id 过滤
  → Gateway 按 workspace_id 隔离缓存、RPM/TPM、预算和成本
```

Access Token 默认 15 分钟，Refresh Token 默认 7 天，使用 HS256 签名。Access Token 还包含 `iat`、`exp`、`jti` 和 `type=access`；Refresh Token 只包含用户身份和 Token 元数据。

注册并不是只插入一条 User。接口先用 `select(User).where(User.email == req.email)` 查重，冲突直接返回 409；密码通过 `bcrypt.gensalt()` 生成随机盐，再用 `hashpw()` 保存哈希字符串，不保存明文。随后在同一个 `AsyncSession` 中依次创建 User、默认 Organization、个人 Workspace、admin Role 和 TeamMember，每一步用 `flush()` 取得数据库生成的 ID，全部完成后只 `commit()` 一次。因此中途抛异常时不会留下“有用户但没有工作空间”的半套数据。组织和工作空间 slug 当前分别使用 `org-{user.id[:8]}`、`ws-{user.id[:8]}`；默认组织是 free plan，默认角色写入 11 项权限。

登录时先按邮箱取 User，再用 `bcrypt.checkpw()` 做常量级库实现的密码核验；用户不存在与密码错误统一返回 401，避免暴露邮箱是否注册，非 active 用户返回 403。工作空间选择逻辑不是由客户端在登录时指定，而是查询该用户所有 TeamMember，按 `created_at desc` 取第一条，也就是最近加入的工作空间；再分别查询 Workspace 得到 org_id、查询 Role 得到 permissions。没有成员关系时仍可登录，但 access token 中 org_id、ws_id 和 permissions 都为空，后续需要 workspace 或权限的接口会被依赖拒绝。

`TokenManager.create_access_token()` 把 `sub`、`org_id`、`ws_id`、permissions、签发时间、过期时间、随机 UUID `jti` 和 `type=access` 编进 JWT；Refresh Token 只保存 `sub/iat/exp/jti/type=refresh`。`verify_token()` 调用 python-jose 的 `jwt.decode(..., algorithms=["HS256"])`，签名错误、过期或格式异常统一捕获为 `None`，中间件不会直接报错，而是让 scope 保持匿名值，真正要求登录的路由再由 `get_current_user` 返回 401。

请求进入后，`AuthMiddleware` 从 Bearer Token 验签并把 user、org、workspace、permissions 写入 ASGI `request.scope`。`WorkspaceContextMiddleware` 只有在 JWT 没有 ws_id 时才允许从 `X-Workspace-ID` 或查询参数补充，避免请求头覆盖 Token 中已经认证的工作空间。

具体来说，两个中间件都先用 `setdefault` 初始化 `auth.user_id`、`auth.org_id`、`auth.ws_id`、`auth.permissions`。认证中间件只识别严格以 `Bearer` 开头的 Header，验证失败也不在中间件返回响应；WorkspaceContextMiddleware 按“Token 中的 ws_id → `X-Workspace-ID` → `?ws_id=`”的优先级补上下文。这个处理解决了上下文传递问题，但 Header/查询参数只是一个字符串，并没有在中间件查询 TeamMember，所以不能把“取得 workspace_id”和“证明用户属于该 workspace”混为一件事。

路由通过 `get_current_user` 强制已登录，通过 `require_permission("model_config:update")` 等依赖做权限判断。权限是 `workspace:read`、`prd:update` 这类字符串集合，角色负责聚合权限，属于 RBAC；workspace membership 检查可以作为资源属性判断，形成简单 ABAC。

权限检查本身非常直接：`require_permission()` 从 scope 取权限数组，做一次 `required in user_permissions`，失败抛 `PermissionDeniedError`。`PermissionChecker` 还提供 admin/editor/viewer 三组系统权限、`workspace_id in user_workspaces` 和“任一权限满足”的辅助方法，但不会自动查询数据库，也不支持通配符和继承。因此权限是否可靠取决于两点：签发 Token 时装入的权限是否最新，以及每条资源路由是否同时做了 workspace 所有权过滤。

租户上下文还向下影响：

- Neo4j 和 PGVector 查询携带 workspace_id。
- 预算和限流按 workspace_id 统计。
- PromptManager 按“组织精确 Agent/Node → 组织 Agent 通配 → 系统默认”选择 Prompt。
- 文档对象路径和数据库记录包含 workspace_id。

PromptManager 先用 `{org_id}:{agent}:{node}` 查内存缓存；未命中时先查组织下精确节点，再查同 Agent 的 `*` 通配模板，最后从硬编码 `DEFAULT_PROMPTS` 取默认值，不存在时返回通用“你是一个 AI 助手”。租户模板变量与调用方 `extra_vars` 合并，后者优先，再交给 PromptRenderer 渲染。新增、更新或删除模板会清空整份本地缓存；它目前是进程内缓存，横向部署时还需要广播失效，否则不同实例可能短时间使用不同 Prompt。

`workspace_id` 不只是数据库过滤条件，也是 Gateway 的治理主键。请求经过认证和 WorkspaceContextMiddleware 后，Gateway 用它隔离语义缓存，维护每个工作空间的 RPM/TPM 窗口，检查周/月预算，并把成本日志归属到正确租户。请求指定的 Provider、model、timeout、estimated_tokens 和 max_tokens 则放入 `gateway_request_context`，后台 `asyncio.create_task` 创建时可继承这些覆盖。

可以把这条链概括为：JWT 确认身份和租户，业务查询用 workspace_id 隔离数据，Gateway 用同一个 workspace_id 隔离模型资源和费用。若某条后台链漏传 workspace_id，即使数据库查询仍安全，缓存、限流和预算也可能退化到默认桶，所以租户上下文必须端到端传递。

### 当前实现边界

- Refresh Token 刷新时只根据 user_id 创建新 Access Token，没有重新装载 org_id、ws_id 和 permissions，刷新后租户与权限声明会丢失。
- `/logout` 只通知客户端清除 Token，没有服务端黑名单或 Refresh Token 吊销。
- `require_permission` 当前主要用于模型配置等少数路由，不是所有业务资源都统一接入了权限依赖。
- WorkspaceContextMiddleware 在 Token 没有 ws_id 时接受请求头值，但不在中间件内校验用户 membership，资源路由仍需做所有权检查。
- JWT 中的 permissions 是登录时快照。管理员修改角色权限后，旧 Access Token 在最多 15 分钟内仍保留旧权限；高风险操作应查询实时权限、缩短有效期或引入 token_version。
- 登录默认选择最近加入的一个 workspace，没有实现显式切换工作空间后重新签发带新 org/ws/permissions 的 Token；多工作空间场景需要专门的 switch-workspace 流程。

### 面试话术

> 认证使用短期 Access Token 和长期 Refresh Token，密码用 bcrypt。JWT 中携带组织、工作空间和权限，中间件只负责解析上下文，路由依赖负责强制认证和权限判断。workspace_id 继续贯穿文档、向量检索、预算、限流和 Prompt 管理。当前刷新后的权限重载、Token 吊销和资源级权限覆盖仍是需要补强的地方。

常见追问：

- __RBAC 和 ABAC 在这里怎么体现？__ Role 聚合权限字符串属于 RBAC；再结合 workspace membership、资源 workspace_id 判断是否能操作具体对象，属于属性约束。
- __为什么不允许请求头覆盖 JWT 中的 workspace？__ 否则用户可能拿合法 Token 后通过改 Header 越权到别的租户。只有 Token 没有 ws_id 时才接受补充值，而且资源层仍需验证 membership。
- __数据隔离只靠数据库 where 条件够吗？__ 不够。Neo4j、PGVector、对象路径、Prompt、缓存、限流、预算和成本都要使用同一个 workspace_id，任何一层漏传都会形成串数据或资源抢占风险。
- __Refresh Token 当前有什么问题？__ 刷新时只按 user_id 签发新 Access Token，没有重新装载 org、workspace 和 permissions，刷新后声明会丢失；应重新查询当前 membership/role 后签发。
- __退出登录为什么不能只让前端删 Token？__ 已泄露的 Refresh Token 在过期前仍可使用；生产系统需要 Token version、jti 黑名单或服务端 Refresh Token 存储与撤销。
- __为什么权限既放 JWT 又要查资源归属？__ JWT 权限回答“能不能做某类操作”，资源归属回答“能不能操作这一条数据”。拥有 `prd:update` 不等于能修改其他 workspace 的 PRD，两者缺一不可。
- __注册为什么多次 flush、最后一次 commit？__ flush 让后续对象拿到 User、Organization、Workspace、Role 的 ID，但仍处于同一事务；最后统一 commit 才保证五类记录原子落库。

关键文件：`app/api/routes/auth.py`、`app/auth/token_manager.py`、`app/auth/middleware.py`、`app/auth/deps.py`、`app/auth/permissions.py`、`app/auth/prompts/manager.py`。

---

## 3.15 可观测性与决策回放链路

### 链路解决什么问题

回答三个问题：一次请求哪里慢、哪个模型调用失败或最贵、Agent 为什么做出当前结果。

### Trace 链路

```text
HTTP 请求
  → http_tracing_middleware 创建 SERVER span
  → LangGraph trace_node 创建 INTERNAL node span
  → Gateway complete/stream_complete 创建 CLIENT span
      → 记录 task_type/layer/node/workspace
      → 记录 cache/guardrail/budget/circuit/failover
      → Provider 调用并记录模型、Token、成本、延迟
  → OTLP BatchSpanProcessor
  → Jaeger
```

HTTP span 记录 method、path、user_id、status 和耗时；图节点 span 记录 node、task_id、workspace_id、layer、iteration 和节点耗时；Gateway span 记录 task_type、Provider、模型、Token、成本、缓存命中、预算降级、熔断和护栏结果。`trace_node()` 会自动判断同步或异步函数，避免节点注册时选错包装器。

Tracer 初始化时把 `service.name` 和固定版本 `0.1.0` 放入 Resource；配置了 OTLP endpoint 才创建 gRPC `OTLPSpanExporter + BatchSpanProcessor`，初始化失败只写 warning，不阻断应用启动。未配置 endpoint 时虽然日志写“使用内存 SpanProcessor”，实际代码没有注册额外 processor，因此本地 Span 不会自动持久化或输出，这是面试中应区分的“创建 Span”和“Span 有地方可查”。

HTTP 中间件以 `http.{METHOD} {path}` 命名 SERVER span，开始时用户信息可能还没经过内层 AuthMiddleware，所以响应返回前会从 scope 再取一次 user_id；正常响应无论 2xx 还是 4xx 当前都设置 OTel 状态为 OK，同时把真实 HTTP 状态码写属性，只有抛异常才设置 ERROR。Prometheus 标签使用路由的原始 `request.url.path`，如果路径含动态 ID，会形成高基数标签，生产环境更适合使用参数化 route template。

`trace_node()` 用 `inspect.iscoroutinefunction()` 选择同步或异步包装器。包装器从第一个参数取得 dict state，只摘取 task_id、workspace_id、current_layer、iteration_count，Span 名为 `node.{node_name}`、Kind 为 INTERNAL；用 `time.monotonic()` 计算耗时，成功写 `duration_ms`，异常时 `record_exception()` 后原样抛出。主图、Analysis、Planning、Generation、Evaluation 的节点注册时都套了该装饰器，所以能定位到具体 section_writer、constraint 或 security 节点，而不只看到一整个 LangGraph 调用。

Gateway 的非流式调用在整次 `complete()` 外创建 `gateway.complete.{task_type}` CLIENT span，初始属性包括 task_type、workspace、layer、node、主 Provider 和模型。输入被护栏拦截会写 `guardrail_blocked`；限流写 `rate_limited/retry_after`；预算降级写 original/downgraded model；缓存、熔断、全部 Provider 失败和输出掩码也分别写属性；成功后再用实际模型覆盖 model，并记录 input/output token 与 cost。流式链路则为每个 Failover 目标创建 CLIENT span，并额外记录 `failover_attempt`，所以可以看到第几次尝试、哪家 Provider 最终成功。

### Metrics 链路

```text
业务代码更新 Counter/Gauge/Histogram
  → GET /api/v1/metrics
  → Prometheus 拉取
  → Grafana 展示与告警
```

核心指标包括：

- `llm_calls_total{model,layer,node}`：模型调用次数。
- `llm_cost_total_usd{model}`：累计模型成本。
- `llm_latency_seconds{model}`：模型延迟分布。
- `llm_tokens_total{model,type}`：输入/输出 Token。
- HTTP 请求量与耗时。
- 任务创建、完成、失败数量和任务总耗时。
- workspace 维度的会话数、文档数和存储量。

`track_llm_call` 使用 context manager，即使内部调用异常也会在 finally 记录延迟；实际 Token 由调用完成后回填。Gateway 还把每次真实成本写入 PostgreSQL `llm_call_logs`，供预算控制读取当前周/月累计用量。

指标的代码行为也有明确边界。调用一进入 `track_llm_call()` 就递增 `llm_calls_total`；离开上下文时观察延迟，只有调用方成功把 input/output_tokens 回填到字典后才累计 Token。输入护栏和限流在进入该上下文之前被提前返回，因此 Gateway 会手动用空 model 标签补记一次调用数。成本 Counter 不在 context manager 内自动计算，而是成功取得 Provider usage 后由 Gateway 的 CostTracker 计算并执行 `LLM_COST_TOTAL.labels(actual_model).inc(cost)`。

Histogram 桶是手工设置的：LLM 延迟覆盖 0.1～30 秒，HTTP 延迟覆盖 0.01～10 秒，任务耗时覆盖 10～1800 秒。`/api/v1/metrics` 直接调用 prometheus-client 的 `generate_latest()` 暴露当前进程指标。单进程部署没有问题；多 Worker 时每个进程有独立内存指标，需要启用 Prometheus multiprocess 模式或让采集端分别抓取，否则聚合值会不完整。

一次 Gateway 调用会留下三类信息：Trace 记录单次调用的 task_type、Provider、模型、缓存、降级、熔断和护栏状态；Prometheus 聚合模型调用量、延迟、Token 和成本；PostgreSQL `llm_call_logs` 保存预算核算需要的真实 usage。缓存命中也应带命中标记，便于解释“为什么这次几乎没有 Provider 延迟和成本”；Failover 则要记录尝试过的目标和最终成功目标，便于区分模型质量问题与供应商故障。

观测数据和业务状态通过 `task_id`、`thread_id`、workspace、layer、node 关联。例如某次 TSD 很慢，可以先从 task span 找到 Generation，再看 `section_writer` 的节点耗时，最后下钻 Gateway span 判断是限流等待、主 Provider 超时后 Failover，还是备用模型本身慢。

### DecisionRecorder 链路

```text
knowledge_retrieval 开始任务 trace
  → 各 Adapter 记录输入摘要、Prompt 摘要、输出变化
  → final_assembly 记录最终结果
  → end_trace 按 task_id 保存 TraceTree
```

它和 OpenTelemetry 的目的不同：OTel 更关心系统调用和性能，DecisionRecorder 更关心 Agent 业务决策，包括输入状态摘要、Prompt、工具、LLM 响应、输出 diff、耗时和 Token。长 Prompt 会截断，列表只保存大小摘要，避免回放数据无限膨胀。

实现上，`start_trace(task_id)` 在 `_current_trace` 字典放入一棵 TraceTree；`record_decision()` 为每步生成 UUID，把 task_id 同时作为 trace_id，并把记录追加到 nodes。第二个节点开始，会把“前一条记录 ID → 当前记录 ID → 当前 agent_name”追加为 edge，因此当前结构本质上是按记录顺序形成的一条链，还不能表达 LangGraph 并行分支和回环的真实拓扑。`end_trace()` 从活动字典弹出 Trace，计算首尾时间差，再以 task_id 写入 ReplayStorage。

状态裁剪有三种规则：输入 State 中超过 200 字符的字符串只保留前 200 字符；列表只写成 `[list:数量]`；其他值原样保留。Prompt 超过 2000 字符时保留首尾各 1000 字符并省略中间；output diff 只保存发生变化的 key，其中 list/dict 只记录类型、大小和 changed 标记，标量保存实际值。需要注意，`llm_response`、tools 和输入 State 中嵌套的 dict 当前没有统一截断或脱敏，因此“已经控制回放体积和敏感信息”只能说部分做到。

从第二条决策起，Recorder 会用 `asyncio.create_task()` 异步调用 Gateway 的 `decision_summary` 路由，只把 Prompt/响应各前 200 字符以及工具名送去生成一句摘要；失败则退化为 `agent.node`。这个后台摘要没有 await，也没有在生成后再次显式保存 record：内存存储因为保存的是对象引用通常能看到后续修改，但换成数据库存储后必须增加 update，否则摘要可能丢失。第一条记录也不会触发摘要任务。

当前主编排只在 Analysis、Planning、Generation、Evaluation 四个 Adapter 调用轻量 `record_node_execution()`。它会把 input_prompt 再截到 1000 字符，工具、原始响应、耗时和 Token 都传空或 0，并捕获所有异常返回 None，确保回放系统故障不影响生成主链。因此数据模型虽然支持完整 LLM/tool 回放，当前装配实际更接近“四阶段状态变更日志”，不能声称每个子节点都已记录完整 Prompt 和原始响应。

### 异步任务的观测难点

`asyncio.create_task` 会复制当前 `contextvars`，但创建任务的 HTTP 请求通常很快返回，HTTP 根 span 会早于后台任务结束。后台 span 不一定在 Jaeger 中呈现为一棵生命周期完整的同步调用树，因此排查长任务时应优先用稳定的 `task_id`、`thread_id`、workspace_id 和日志字段关联，而不是只依赖父子 span。

### 当前实现边界

- DecisionRecorder 默认是内存存储，进程重启后回放记录丢失；生产环境应持久化或写入专门观测存储。
- Recorder 当前主要记录编排层 Adapter，并没有自动覆盖每个子图节点的完整输入输出。
- Prompt 和响应记录涉及敏感信息，生产环境需要与 Gateway 脱敏策略、访问权限和保留周期统一治理。
- 未配置 OTLP endpoint 时没有实际导出 processor；日志中的“内存 SpanProcessor”不能等同于有可查询的本地 Trace 后端。
- HTTP 指标使用原始 URL path，动态资源 ID 可能造成 Prometheus 标签高基数；应记录路由模板而不是实例路径。
- DecisionRecorder 的异步摘要采用 fire-and-forget，持久化存储下还缺摘要完成后的 update 与进程退出前 drain。

### 面试话术

> 可观测性分三层：HTTP 根 span 看入口，LangGraph node span 看哪个节点慢，Gateway CLIENT span 看实际 Provider、模型、Token、成本、缓存和护栏；Prometheus/Grafana 做聚合指标，DecisionRecorder 按 task_id 保存 Agent 状态变化和决策过程。后台任务的生命周期长于 HTTP span，所以实际排查以 task_id 关联最可靠。

常见追问：

- __Trace、Metrics、DecisionRecorder 有什么区别？__ Trace 看一次请求经过哪些组件和耗时；Metrics 看整体趋势与告警；DecisionRecorder 看 Agent 输入、Prompt 摘要、状态变化和为何走某条业务分支。
- __一次请求很慢怎么排查？__ 用 task_id 找主任务，再定位最慢 layer/node，最后查看 Gateway span 是限流、缓存未命中、主 Provider 超时并 Failover，还是模型本身延迟高。
- __成本怎么做到可归因？__ Gateway 从 Provider usage 得到输入/输出 Token，按模型价格计算并写调用日志，同时打上 workspace、task_type、layer、node；这样能聚合到租户和业务节点。
- __为什么异步任务的 Trace 容易断？__ 创建后台任务后 HTTP 根 span 很快结束，后台执行生命周期更长；需要显式传播 trace context，并用 task_id/thread_id 作为稳定关联字段。
- __记录 Prompt 会不会泄密？__ 会有风险。应沿用 Gateway 脱敏、限制 Recorder 访问权限、截断长内容并设置保留周期；生产环境不应无条件保存原始 Prompt 和响应。
- __为什么 Trace 有 Span 却在 Jaeger 查不到？__ Span 创建和导出是两回事；只有 OTLP endpoint 配置成功并注册 BatchSpanProcessor 后才会送到 Jaeger，未配置时当前实现没有可查询的本地导出器。
- __DecisionRecorder 能完全复现一次任务吗？__ 当前不能。它主要记录四个 Adapter 的裁剪状态，工具、原始响应和 Token 多为空，也没有保存模型版本、随机参数及完整并行拓扑；它适合解释阶段变化，不是严格确定性重放。

关键文件：`app/observability/tracing.py`、`app/observability/metrics.py`、`app/observability/replay/recorder.py`、`app/llm_gateway/__init__.py`、`app/task_manager.py`、`app/main.py`。

---

## 面试串讲：把 3.1–3.15 连成一条线

> 用户从统一 `/interact` 入口提交 PRD，系统先完成认证和 workspace 上下文注入，再用规则加 LLM 兜底识别意图。复杂生成交给 TaskManager 后台执行，LangGraph 主图先恢复会话记忆并从 Neo4j、PGVector 做混合知识检索，经过查询改写、RRF、反思和重排得到上下文。随后 Analysis 结构化需求，Planning 生成架构规划，Generation 用 Send 并行生成章节，Evaluation 用九个并行节点评分并决定是否迭代。分析和规划后可以 interrupt 等待人工审核，通过 thread_id 和 checkpoint 恢复。所有模型调用统一走 Gateway，处理护栏、限流、路由、预算、语义缓存、熔断、Failover 和成本；执行过程通过 SSE 推送，通过 OTel、Prometheus 和 DecisionRecorder 观测，最终压缩会话记忆并落库。

如果面试官继续追问，优先展开以下四点：

1. 为什么用 StateGraph：长流程需要条件分支、循环、暂停和恢复。
2. 为什么 Neo4j + PGVector：图关系和语义相似度是两种不同检索能力。
3. 为什么需要 Gateway：几十个 LLM 节点必须统一治理安全、稳定性和成本。
4. 为什么使用 Send + reducer：并行降低耗时，reducer 避免共享状态写冲突。
