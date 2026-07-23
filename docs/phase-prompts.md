# PRD2TechSpec 需求拆分索引

> **5 个独立需求文档**，每个文档包含完整的：需求描述、目标、验收标准、技术栈、Coding 约束、完整链路、模块联通、测试用例、数据结构和新增文件。
>
> 每个文档可直接喂给 AI，无需阅读总文档 `prd2tsd.md`。

---

## 快速开始

```mermaid
flowchart LR
    A[block-A] --> B[block-B]
    B --> C[block-C]
    C --> D[block-D]
    D --> E[block-E]
```

**必须按 A → B → C → D → E 顺序进行。** 每块开始时，前一块的 `pytest tests/ -v` 必须全绿。

---

## 文档列表

| 块 | 文件 | 天数 | 新增容器 | 做什么 |
|----|------|------|---------|--------|
| **A** | [`docs/block-A-infrastructure.md`](block-A-infrastructure.md) | 3-5 | postgres | 项目脚手架 + 质量门禁 + 数据模型 + Auth多租户 + **LLM Gateway核心** + **数据安全(脱敏/审计)** + **CI/CD** + API骨架 |
| **B** | [`docs/block-B-knowledge-layer.md`](block-B-knowledge-layer.md) | 3-5 | neo4j | 文档→图谱构建 + **实体融合/消歧** + **Claims提取** + **Embedding** + **版本控制** + **老化策略** + Local/Global Search |
| **C** | [`docs/block-C-agent-pipeline.md`](block-C-agent-pipeline.md) | 5-7 | 0 | 4个Agent Layer + **多语言支持** + **质量评分** + **工作量估算** + **干系人分析** + **成本估算** + **时间线** + **技能缺口** + **风险量化** + **模板系统** + **多格式导出** + **评分校准** |
| **D** | [`docs/block-D-orchestration.md`](block-D-orchestration.md) | 3-5 | 0 | Orchestrator 串联 + API 路由 + 端到端 |
| **E** | [`docs/block-E-enterprise.md`](block-E-enterprise.md) | 3-5 | jaeger+prom+minio+redis | LLM Gateway增强 + 观测性 + 会话历史 + 文档管理 + **CSV双通路索引** + **Web爬虫** + **CLIP多模态** + **协作文档** + **批量任务** + **搜索回退** + 集成生态 |

---

## 使用方式

```bash
# 1. 打开对应块的文档
code docs/block-A-infrastructure.md

# 2. 把整份文档作为第一条消息喂给 AI
# 3. AI 编码完成后，运行验收测试
pytest tests/ -v --tb=short

# 4. 所有测试通过后，进入下一块
```

每个文档都是完整自包含的：
- ✅ 不需要打开 `prd2tsd.md`
- ✅ AI 只需要读这一份文档就能编码
- ✅ 包含了所有需要的约束和标准
- ✅ 与前一块的联通有明确测试覆盖

---

## 关联总文档

每份块文档的顶部都标记了对应的 `prd2tsd.md` 章节，方便需要查阅完整设计时回溯。

| 块 | prd2tsd.md 对应章节 |
|----|-------------------|
| A | §1.1 + §1.2(核心) + §8 + §9.1/9.2(auth) + §11 + §13 |
| B | §三(完整) |
| C | §四 + §五 + §六 + §七(完整) |
| D | §二 + §9.2(generate/review/evaluate) |
| E | §1.2(增强) + §1.3 + §3.6/3.7 + §12(完整) |
