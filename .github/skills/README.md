# Skills 使用指南

> Skills 重构完成。`ai-coding-rules` 精简为纯编码规范入口，`workflow` 作为闭环统筹者调度所有 skill。

## Skill 一览

| Skill | 路径 | 触发关键词 | 加载时机 |
|-------|------|-----------|---------|
| **`workflow`** 🌀 | `workflow/SKILL.md` | `workflow`, `开发`, `需求`, `任务`, `帮我做` | **任何开发任务的首选入口**。自动判断任务类型，调度对应 skill |
| **`ai-coding-rules`** 🧠 | `ai-coding-rules/SKILL.md` | `编码`, `写代码`, `修 bug`, `implement`, `coding` | 编码实现（语言规范 + 通用约束）。被 `workflow` 调度 |
| **`debug-tools`** 🛠️ | `testing/debug-tools/README.md` | （非独立 skill，由 `testing` 加载） | 调试工具包（非独立 skill），由 `testing` 加载。含调试脚本和排查流程 |
| **`testing`** 🧪 | `testing/SKILL.md` | `test`, `testing`, `测试`, `unit test`, `integration test`, `e2e`, `smoke test`, `写测试` | 编写测试、补充测试覆盖、测试验证 |
| **`refactor`** 🔧 | `refactor/SKILL.md` | `refactor`, `重构`, `架构变更`, `跨模块修改`, `改造` | 代码重构、架构变更、跨模块修改 |
| **`api-design`** 🌐 | `api-design/SKILL.md` | `API`, `接口`, `端点`, `REST`, `endpoint`, `MCP 工具` | API 设计、端点定义、REST 接口评审 |
| **`database`** 🗄️ | `database/SKILL.md` | `数据库`, `ORM`, `SQL`, `查询`, `迁移`, `model`, `database` | 数据库设计、ORM 模型、查询优化、迁移 |
| **`performance`** ⚡ | `performance/SKILL.md` | `性能`, `优化`, `profiling`, `延迟`, `渲染`, `bundle`, `performance` | 性能优化、Profiling、前端渲染优化 |
| **`security`** 🛡️ | `security/SKILL.md` | `安全`, `认证`, `密钥`, `XSS`, `SQL注入`, `加密`, `security` | 安全编码、密钥管理、漏洞防护 |
| **`error-handling`** ⚠️ | `error-handling/SKILL.md` | `错误处理`, `异常`, `降级`, `fallback`, `error handling`, `容错` | 错误处理架构、优雅降级、生产日志 |
| **`prototype`** ⚡ | `prototype/SKILL.md` | `原型`, `prototype`, `MVP`, `PoC`, `Hackathon`, `demo`, `快速验证` | 快速原型、MVP、PoC、Hackathon |
| **`doc`** 📖 | `doc/SKILL.md` | `文档`, `README`, `ADR`, `文档规范`, `doc`, `documentation` | 文档体系设计、技术文档编写、ADR |
| **`product-design`** 🎨 | `product-design/SKILL.md` | `产品`, `需求`, `功能优先级`, `用户研究`, `产品设计` | 产品设计讨论、需求分析、功能优先级 |
| **`architecture`** 🏗️ | `architecture/SKILL.md` | `架构`, `技术选型`, `系统设计`, `ADR`, `architecture` | 系统架构设计、技术选型、ADR |
| **`code-review`** 🔍 | `code-review/SKILL.md` | `review`, `code review`, `审查`, `评审`, `CR`, `审计`, `帮我看看代码` | 代码审查/评审/审计 |
| **`simplify`** ✂️ | `simplify/SKILL.md` | `simplify`, `简化`, `精简`, `去重`, `代码瘦身`, `简化代码`, `reduce complexity` | 代码简化、去重、降复杂度 |
| **`grill-me`** 🔥 | `grill-me/SKILL.md` | `grill me`, `拷问`, `盘问`, `面试`, `拷打`, `自省`, `self-grill`, `challenge me` | 任务自省/拷问。复杂任务完成后自动触发 |
| **`git`** 📝 | `git/SKILL.md` | `git`, `commit`, `提交`, `push`, `推送`, `rebase`, `merge`, `git 操作` | git 操作（提交/推送/rebase/merge 等） |
| **`release`** 🚀 | `release/SKILL.md` | `release`, `发布`, `版本号`, `changelog`, `发版`, `publish` | 发布管理、版本号变更、Changelog |
| **`graphify`** 🔗 | `graphify/SKILL.md` | `graphify`, `知识图谱`, `架构分析`, `代码关系`, `graph query` | 架构关系分析、知识图谱查询 |
| **`prompt`** 🤖 | `prompt/SKILL.md` | `prompt`, `提示词`, `vibe coding`, `生成代码`, `prompt 模板` | AI 提示词编写、Prompt 模板 |

## 工作流

```
用户需求 → workflow(调度) → 对应 skill(执行) → 验证 → grill-me(自省) → git(提交)
```

## 文档约束

设计文档 → `docs/` | 开发记录 → `overview.md` | 自省记录 → `grill-self-review.md`