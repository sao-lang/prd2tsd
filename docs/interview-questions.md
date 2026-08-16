# PRD2TSD Agents — 面试要点与问答

> **版本**: v1.0
> **日期**: 2026-08-14
> **说明**: 本文档为 `docs/full-architecture-deep-dive.md`（全链路架构文档）的面试专题部分迁移而成，
> 内容基于 2026-08-13 代码库真实状态更新（含 Block E 统一交互入口 / WP1 观测 / WP2 评测 / 社区检测简化）。
> 系统架构细节请阅读主文档。

---

## 目录

- [一、项目核心卖点总结](#一项目核心卖点总结)
- [二、与业界方案深度对比](#二与业界方案深度对比)
- [三、面试常见追问及回答模板](#三面试常见追问及回答模板)
- [四、可深挖的方向](#四可深挖的方向)

---

## 一、项目核心卖点总结

### 1.1 项目亮点（一句话版本）

| # | 亮点 | 适合面试展开的点 |
|---|------|----------------|
| 1 | **LangGraph + LangChain 混合架构** | "为什么不用纯 LangChain AgentExecutor？因为我们需要精确控制每个步骤、支持 Human-in-the-Loop、支持 checkpoint 持久化。LangGraph 做图编排（主编排图 15 节点 + 4 个 Layer 子图），LangChain 做节点内部的 LLM 调用和结构化输出（ChatPromptTemplate + PydanticOutputParser）。" |
| 2 | **PostgreSQL Checkpointer** | "传统的 Agent 系统崩溃后状态全丢。我们用 PostgresSaver 把每一步状态持久化到 PG（lifespan 初始化，失败降级 MemorySaver），崩溃后可从最近 checkpoint 恢复续跑。thread_id 绑定 sessions 表，会话续接自动恢复图状态。" |
| 3 | **自研 LLM Gateway** | "封装的不是简单 API 调用，而是整套生产级能力：7 个护栏插件（pre_llm 3 + post_llm 4）、Provider Failover 链（deepseek-chat → gpt-4o-mini）、Circuit Breaker 熔断（每 Provider 独立，3 次失败熔断 30s）、语义缓存、成本追踪、速率限制（RPM/TPM 滑动窗口）、预算控制（90% 自动降级）。" |
| 4 | **实体增强双路检索 + 反思** | "不是简单 RAG。做了 Neo4j 知识图谱（实体 + 关系子图遍历） + PGVector 向量双路检索，还有 ReflectionJudge 自我纠偏——检索结果不好就修正查询重新检索（最多 3 轮），最后 Cross-encoder 精排 + token 预算压缩。" |
| 5 | **Human-in-the-Loop** | "关键节点（需求分析、架构规划）用 LangGraph 的 interrupt() 暂停等待人工审核，审核通过后通过 Command(resume=...) 无缝恢复（interrupt 返回值 = resume_value）。审核 API + SSE 实时推送审核请求。" |
| 6 | **SSE 流式推送** | "EventBus 基于 asyncio.Queue 的非阻塞 Pub/Sub（queue maxsize=128 防内存爆炸），15+ 种事件类型覆盖全生命周期。用户看到实时进度、流式文档生成（SectionWriter 逐 token + 每 200 字符推送）、审核通知、30s 心跳。" |
| 7 | **迭代闭环** | "评测层给方案打分，低于 85 分自动回退重规划/重生成，最多 3 轮迭代。Evaluation 用 LangGraph Send() 并行扇出 9 个评测节点（总耗时=max 而非 sum），评分合并 + 历史校准。" |
| 8 | **统一交互入口** | "/chat、/generate、/qna/stream 等 6 个端点全部收敛到 POST /api/v1/interact，IntentClassifier（规则 + LLM 两级）判定 chat/knowledge_qa/document_analysis/complex_generation/clarification 后分流。消除双实现——路由层预写意图，图内 classify 幂等跳过。" |
| 9 | **评测闭环（WP2）** | "引入 deepeval 4.x 做 RAG 评测（L1: context_precision/recall，L2: faithfulness/relevancy）+ 反思 A/B 对比；Agent 评测分 L3 过程指标（完成率/迭代/人工介入率）和 L4 结果 rubric judge。评测报告反哺检索参数与 Agent 流程优化。" |
| 10 | **多租户 + RBAC/ABAC** | "资源级权限（workspace:/prd:/model_config:），工作空间级别隔离。三级 Prompt 隔离（组织自定义 → Agent 级通配 → 系统默认）。数据分级脱敏（L1-L4，API Key/Token 替换为 [MASKED_XXX]）+ 哈希链审计日志。" |

### 1.2 技术深度的体现（可展开点）

```text
1. LangGraph 图结构设计:
   - 为什么用 StateGraph 而不是 MessageGraph？
   - 条件路由（add_conditional_edges）vs Command() 路由的适用场景
   - PostgresSaver checkpoint 机制原理（每节点执行后写入、崩溃恢复、Time-Travel）
   - astream vs ainvoke 的使用场景差异
   - Send() 并行扇出: Evaluation 9 节点 + Generation section_writer

2. LLM 调用的完整链路:
   - 7 个护栏插件的注册与执行顺序
   - Circuit Breaker 状态机 + Failover 链协同
   - 为什么用 GatewayChatModel 包装而不是直接用 langchain-openai

3. 知识检索架构:
   - Local Search 与 Global Search 的区别和适用场景
   - ReflectionJudge 自我纠偏机制（最多 3 轮）
   - Neo4j 图遍历 + PGVector 向量检索融合（RRF k=60）
   - 社区检测为何简化（未兑现的复杂逻辑及时删除）

4. 工程实践:
   - Config/State/Runtime 三层分离设计
   - Adapter 模式做 Layer 解耦
   - EventBus 的 asyncio.Queue 非阻塞设计
   - 统一交互入口的意图分流 + 幂等化
   - 评测闭环（deepeval + rubric judge）如何反哺优化
```

---

## 二、与业界方案深度对比

| 维度 | PRD2TSD Agents | LangChain AgentExecutor | AutoGPT | MetaGPT | CrewAI |
|------|---------------|------------------------|---------|---------|--------|
| **编排方式** | LangGraph 显式 StateGraph | 隐式 ReAct 循环 | 隐式循环 | 隐式角色扮演 | 隐式任务委派 |
| **可控性** | 100%（每个步骤显式定义） | 低（黑盒决策） | 低 | 中（SOP 定义） | 中 |
| **Human-in-the-Loop** | ✅ 原生 interrupt/resume | ❌ 需自行实现 | ❌ | ❌ | ❌ |
| **Checkpoint 持久化** | ✅ PostgreSQL（PostgresSaver） | ⚠️ 可选 SQLite | ❌ | ❌ | ❌ |
| **崩溃恢复** | ✅ 从 checkpoint 续传 | ❌ | ❌ | ❌ | ❌ |
| **多租户隔离** | ✅ RBAC + ABAC | ❌ | ❌ | ❌ | ❌ |
| **SSE 流式推送** | ✅ 15+ 事件类型 | ⚠️ 仅 LLM token 流 | ❌ | ❌ | ⚠️ 基础 |
| **护栏安全** | ✅ 7 个可插拔护栏 | ❌ | ❌ | ❌ | ❌ |
| **熔断降级** | ✅ Circuit Breaker + Failover 链 | ❌ | ❌ | ❌ | ❌ |
| **知识检索** | ✅ Neo4j+PGVector 双路 + Reflection | ⚠️ 基础 RAG | ⚠️ 基础向量 | ⚠️ 基础 | ⚠️ 基础 |
| **迭代自评** | ✅ 10 维评分 + 校准 + 自动回退 | ❌ | ❌ | ❌ | ❌ |
| **多模型路由** | ✅ Gateway 统一管理多 Provider | ⚠️ 单一 Provider | ⚠️ 单一 | ⚠️ 单一 | ⚠️ 单一 |
| **评测闭环** | ✅ deepeval RAG 评测 + Agent rubric 评测 | ❌ | ❌ | ❌ | ❌ |
| **统一交互入口** | ✅ 对话/提问/文档分析/生成单一入口 | ❌ | ❌ | ❌ | ❌ |

---

## 三、面试常见追问及回答模板

### Q1: 为什么不用纯 LangChain 做 Agent？

```text
LangChain 的 AgentExecutor 是黑盒的 ReAct 循环。给它 prompt 和一组工具，
它自己在内部循环"思考→行动→观察→思考..."直到完成。

问题在于：
1. 无法精确控制每一步做什么——AgentExecutor 自己决定何时调工具、何时退出
2. 无法在中间插入 Human-in-the-Loop——没有原生 interrupt/resume 机制
3. 无法做崩溃恢复——AgentExecutor 没有 checkpoint 概念

我们的方案：
- 用 LangGraph StateGraph 替代 AgentExecutor——显式定义每个节点和每条边
- 每个节点就是一个 Python async 函数，行为完全可控
- 用 interrupt() 和 Command(resume=...) 做人工审核
- 用 PostgresSaver 做崩溃恢复
- 节点内部用 ChatPromptTemplate + GatewayChatModel + PydanticOutputParser 做结构化 LLM 调用
- 分工：LangGraph 负责"图怎么走"，LangChain 负责"节点内部 LLM 怎么调"
```

### Q2: PostgresSaver vs MemorySaver 的区别和选择？

```text
MemorySaver 是 LangGraph 默认 checkpointer，纯内存实现。
  优点：零配置、测试方便
  缺点：重启全丢，不适合生产

PostgresSaver 把每一步 checkpoint 写入 PostgreSQL 的 langgraph_checkpoints 表。
  优点：
  1. 崩溃恢复：服务重启用相同 thread_id 继续跑，自动从最近 checkpoint 恢复
  2. 多线程安全：多请求可并发操作不同 thread
  3. Time-Travel 调试：get_state 查看历史状态、update_state 修改历史状态
  4. 与 sessions 表 thread_id 绑定：会话续接自动恢复图状态
  代价：
  - 每次 checkpoint 有一次 PG 写入（LangGraph 已优化为批量写入）
  - 需要 PostgreSQL 运行

我们的实现：lifespan 中 create_postgres_checkpointer()，初始化失败降级 MemorySaver（开发模式）
```

### Q3: Adapter 模式为什么重要？为什么不让 Layer 直接操作 OrchestratorState？

```text
核心原因：保持 Layer 独立性，使其可独立编译、独立测试。

如果 Planning Node 直接 import OrchestratorState：
- Planning Layer 单测需构造完整 OrchestratorState
- 改 OrchestratorState 结构会影响所有 Layer
- Layer 之间形成隐式耦合

使用 Adapter 模式：
- 每个 Layer 只知道自己 State 结构（PlanningState）
- Adapter 负责 OrchestratorState ↔ LayerState 映射
- 测试 Layer 时只需构造自己的 State
- 换实现只需换 Adapter 的 graph 引用
- 符合依赖倒置原则

4 个 Adapter（progress 节点）:
  AnalysisAdapter(0.25) / PlanningAdapter(0.50) / GenerationAdapter(0.75) / EvaluationAdapter(0.90)
```

### Q4: 护栏系统为什么放在 Gateway 层而不是每个 LangGraph 节点里？

```text
护栏是 LLM 调用的安全机制，不是某个节点的业务逻辑。

放在 Gateway 层的优势：
1. 统一性：任何节点调 LLM（analysis 的 requirement 还是 generation 的 section_writer）
   都经过同一套护栏
2. pre_llm / post_llm 两阶段执行顺序由 Gateway 统一管理:
   PromptInjection → PII → Timeout → [LLM Call] → ContentSafety → OutputValidator
   → EmptyResponse → RetryDecision
3. 新增护栏只需在 Gateway 初始化时 register，不需要改图结构
4. 护栏结果驱动路由: GuardrailResult.metadata（retry/fallback_model/max_retries）
   可供 LangGraph 条件路由决策（空响应 → metadata.retry=True → 路由到 retry）
5. 护栏拦截/限流/全失败路径都会记录 llm_calls_total，避免指标低估
```

### Q5: 如果有 100 个并发任务，系统怎么处理？

```text
1. 任务创建层：TaskManager.create_task 立即返回 task_id，asyncio.create_task 后台协程
2. 数据库连接池：PostgreSQL pool_size=10 + max_overflow=20（asyncpg 自动管理）
3. LLM 调用限流：RateLimiter 按 workspace 维度限制 RPM(60)/TPM(100000)，超限排队/返回提示
4. 熔断保护：Provider 连续失败 3 次 → CircuitBreaker OPEN，后续请求直接失败不继续打挂掉的 Provider
5. Failover 链：Primary 不可用 → 自动切 Fallback；全不可用 → 降级响应
6. 预算控制：月预算超 90% → 自动降级低成本模型
7. 定时任务解耦：知识图谱刷新/会话清理/Web 同步走 Celery Worker 独立进程
8. 多租户隔离：workspace 级权限 + Prompt 隔离
```

### Q6: 知识检索的反思机制是怎么工作的？

```text
ReflectionJudge 是知识检索层的自我纠偏机制。

工作流程：
1. 正常检索：IntentRouter → QueryRewriter(≤5 子查询) → QueryEnricher(实体链接)
   → LocalSearch(Neo4j 子图 + PGVector) / GlobalSearch(实体类型聚合 + LLM 宏观总结)
   → RRFFusion(k=60) 融合
2. 反思判断：检索结果 + 原始查询发给 LLM
   Prompt: "这些检索结果满足用户需求吗？如果不满足，缺少什么？给出修正后的搜索查询。"
3. LLM 返回 judgment:
   - accept: 结果满足 → 继续后续流程（重排/压缩）
   - refine: 不满足 → 返回 refined_query
4. refine 则用 refined_query 重新检索，再次反思
5. 最多 3 轮（max_reflection_rounds=2）

示例：
原始查询: "用户服务用什么技术栈？"
检索结果: [关于订单服务的文档...]
反思判断: refine（reason: 缺少用户服务技术栈信息, refined_query: "用户微服务 技术栈 数据库 框架"）
第二轮: 检索命中 [Spring Boot + PostgreSQL + Redis...] → accept

这解决了传统 RAG "第一次检索不准就没辙" 的痛点。
```

### Q7: LangGraph 的 interrupt/resume 机制是怎么实现的？

```text
interrupt() 是一个特殊调用，会：
1. 暂停当前节点执行
2. 将当前 State 写入 Checkpointer（PostgresSaver）
3. 抛出 GraphInterrupt（LangGraph 内部处理，对调用方透明）
4. 调用方（TaskManager）检测到 astream 结束但 status 仍 running
   → 标记任务 paused，推送 task.review_required

恢复时：
1. 调用方用相同 thread_id 重新 astream
2. 传入 Command(resume=resume_value)
3. LangGraph 从 Checkpointer 加载最近 checkpoint
4. 重放已完成的节点（自动跳过）
5. 在 interrupt() 处恢复执行，interrupt() 的返回值就是 resume_value
6. 继续执行后续节点

线程安全保证：
- thread_id 是 checkpoint 唯一标识
- 同一 thread 的多次 astream 自动排队
- PostgresSaver 用 PostgreSQL 行锁保证并发安全

为什么用 Command(resume=value) 而不是直接传参？
- 直接传参会被当作新的初始状态执行（重跑所有节点）
- Command(resume=value) 告诉 LangGraph："这是给上一个被 interrupt() 暂停节点的返回值"
```

### Q8: 这个项目最大的技术挑战是什么？

```text
最大的技术挑战：在 LangGraph 的编排灵活性、LangChain 的节点内便利性、
自研 LLM Gateway 的生产级能力的"不可能三角"中找到平衡。

具体来说：
1. LangGraph 擅长编排，但节点只能接收/返回 State，不提供 LLM 调用能力
2. LangChain 擅长 Prompt 管理和结构化输出，但 ChatOpenAI 没有成本追踪、限流、缓存、护栏
3. 自研 LLM Gateway 有完整生产级能力，但不是 BaseChatModel，无法用于 LCEL 链

解决方案：GatewayChatModel
- 实现 LangChain 的 BaseChatModel 接口（_agenerate / _astream / bind_tools / _generate）
- 内部委托给 LLM Gateway 的 complete() / stream_complete()
- Agent 节点内部可用 LangChain 全部能力（PromptTemplate / OutputParser）
- 同时保留 Gateway 全部生产级能力（限流/缓存/熔断/护栏/成本追踪）
- 且不引入被 tech-stack.yml 禁止的 langchain-openai 包

另一个挑战：统一交互入口
- 多个端点（/chat、/generate、/qna/stream）造成意图判定双实现
- 整改为 POST /api/v1/interact 唯一入口，路由层预写意图 + 图内 classify 幂等跳过
```

### Q9: 评测体系是怎么做的？（WP2）

```text
RAG 评测（app/evaluation/rag/，基于 deepeval 4.x）:
  L1 指标（检索质量）: context_precision / context_recall
  L2 指标（回答质量）: faithfulness / answer_relevancy
  retrieve_and_answer: pipeline.retrieve → 严格基于上下文回答（temperature=0.2）
  反思 A/B: evaluate_ab_reflection() 分别以 reflection=false/true 跑两组完整评测
            → 对比反思开关对指标的影响，指导是否保留反思循环
  CLI: scripts/run_rag_eval.py --dataset --variant --ab-reflection

Agent 评测（app/evaluation/agent/）:
  L3 过程指标: 完成率 / 平均迭代轮数 / 人工介入率 / 耗时
  L4 结果质量: 按 rubric 用 judge LLM（temperature=0）JSON 打分
  _default_runner: 通过主编排图 astream 跑真实任务
  CLI: scripts/run_agent_eval.py

兼容坑: deepeval 4.x 将 click 钉在 <8.4.0，与 huggingface-hub >=8.4.2 冲突
（运行时已验证正常，pip check 会告警）
```

### Q10: 数据脱敏和审计怎么做？（企业级）

```text
数据分级（DataClassifier）:
  L1 公开（email/ip） / L2 内部（password/phone）/ L3 敏感（api_key/token/id_card）/ L4 机密

DataMaskingEngine.mask(text, level):
  按等级正则替换为 [MASKED_API_KEY] 等标记（L3 级别才脱敏 sk-/pk-/coh- 开头的 key）

审计日志（AuditLogger）:
  哈希链不可篡改: 每个条目标记 prev_hash，verify_hash_chain() 校验
  用于 LLM 调用、敏感操作的可追溯审计
```

---

## 四、可深挖的方向

```text
已实现（曾经是"计划"）:
  ✅ Send() 并行扇出 → Evaluation 9 节点并行（Block G）
  ✅ Generation section_writer Send 并行（fan_out_sections）
  ✅ PostgresSaver 生产级持久化（Block G 8.5）

仍可扩展:
  1. 多模态输入（图片架构图 → 直接分析）——CLIP 多模态已删除，可重新规划
  2. 实时协同编辑（WebSocket + OT/CRDT）——协作文档已删除
  3. Agent 市场（社区贡献自定义 Agent Layer）
  4. 方案 A/B 测试（同一 PRD → 不同方案对比评估）
  5. LangGraph 原生 Subgraph（4 个 Layer 作为原生子图，替代手工 Adapter）
  6. Multi-Agent Supervisor 模式（Supervisor + Worker 协商）
  7. Web 同步子图化（修复 sync_web_resources 的 WebIndexer 悬空引用）
  8. 运行时配置化阈值（IterationDecider 85/70 硬编码 → OrchestratorConfig）
  9. RuntimeInjector 接线（恢复 SSE 节点副作用）
```

---

> **文档结束** — PRD2TSD Agents 面试专题。
> 系统架构细节、全链路、API 清单、数据模型见 `docs/full-architecture-deep-dive.md`。
