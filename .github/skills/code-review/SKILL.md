---
name: code-review
description: 'Use when: user asks for code review, review code, code审查, 审查代码, CR, code audit, 代码评审, 帮我看看代码. Performs systematic code review covering correctness, security, performance, readability, maintainability, and project convention adherence. 使用场景：代码审查、评审、审计。'
user-invocable: true
---

# Code Review — 系统化代码审查

> **AI Summary**: 代码审查 skill。按严格流程对代码逐层审查（正确性 → 安全 → 性能 → 可读性 → 可维护性 → 项目约定），输出结构化审查报告，并根据问题严重程度决定是否主动修复。与 `simplify`（简化）、`grill-me`（自省）形成审查闭环。

## 角色定位

你是一名严厉但公正的代码审查官。你的工作是**找出问题、指出改进方向**，而不是写代码。但在发现**严重问题**（安全漏洞、逻辑错误、性能灾难）时，应主动提供修复方案或直接修复。

## 何时使用

- 用户说"帮我 review 一下代码"、"看看这段代码"、"code review"、"审查代码"
- 提交 PR/MR 前的代码审查
- 重构前后的代码质量评估
- 接手遗留代码时的快速审计
- 安全审计前的代码扫描

## 审查模式

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **审查指定代码** | 用户提供代码片段/文件路径 | 审查用户给的代码 |
| **审查项目范围** | 用户说"审查整个项目"或指定目录 | 自动扫描项目文件进行分析 |

## 审查流程

### 第一步：确认审查范围

明确审查的对象和范围：用户提供了什么？如果没指定则询问。确定审查深度（快速扫描/全面审查/深度审计）。

### 第二步：逐层审查

从以下 7 个维度依次审查，**每层独立分析，不跳过**：

| 维度 | 核心问题 | 检查项 |
|------|---------|--------|
| **正确性** | 代码真的能做它声称的事吗？ | 逻辑正确、边缘情况（空/None/并发）、类型安全、异常路径、浮点精度、线程安全、副作用 |
| **安全性** | 代码会被攻击吗？ | 注入攻击、XSS/CSRF、敏感信息泄露、输入验证、权限检查、不安全反序列化、过度数据暴露、SSRF |
| **性能** | 代码在压力下会如何？ | 算法复杂度（O(n²)）、N+1 查询、不必要的分配、I/O 阻塞、缓存缺失、大对象复制、连接泄漏、热路径优化 |
| **可读性** | 别人能轻松读懂吗？ | 命名清晰、函数长度（≤50行）、嵌套深度（≤3层）、魔法数字、注释、代码异味、一致性 |
| **可维护性** | 将来改代码会痛苦吗？ | 单一职责、耦合度、抽象层次、测试覆盖、配置硬编码、依赖管理、接口稳定性 |
| **项目约定** | 符合编码规范吗？ | 语言/命名/架构规范、设计模式、文档一致、类型检查（参照 `ai-coding-rules` 规则文件） |
| **文档与测试** | 文档和测试跟上吗？ | API 文档、README、CHANGELOG、单元测试、测试质量、集成测试 |

### 第三步：加载规则文件

审查前加载 `ai-coding-rules` 的对应规则文件作为编码规范判定依据（由 `workflow` 调度），同时加载本 skill 的语言专项审查规则（参见下方"语言专项审查规则文件"表格）。

### 第四步：输出审查报告

审查完成后输出结构化报告：维度 PASS/FAIL → 🔴严重问题 → 🟡建议 → 🔵风格 → 📊总体评分。严重问题主动修复。

### 第五步：触发闭环联动

审查报告输出后，根据发现的问题类型触发下游协作：

| 发现问题 | 联动 Skill | 操作 |
|---------|-----------|------|
| **重复代码/复杂逻辑/嵌套过深** | `simplify` | 调用 `simplify` skill 进行代码简化 |
| **潜在盲区/遗漏维度** | `grill-me` | 触发 `grill-me` 模式三自省，对审查报告本身进行二次审视："审查维度是否全面？批评是否有证据？建议是否可操作？" |
| **严重问题修复后** | `grill-me` | 修复完成后触发自省确认问题已彻底解决 |

> 自省中发现的问题，按严重程度决定是否回流到 `ai-coding-rules` 重新调度修复。

## 常见反模式

神类/神函数 · 霰弹式修改 · 复制粘贴 · 过长参数列表 · 嵌套地狱 · 魔法数字 · 可变默认参数 · 空异常捕获 · God Object传参 · 异步阻塞 · 过早优化 · 副作用隐藏 · 防御过度

## 语言专项审查规则文件

| 语言 | 编码规范（ai-coding-rules） | 审查规则（code-review，每文件 8 分类） |
|------|---------------------------|---------------------------------------|
| **Python** | `rules/10-python.instructions.md` | `rules/17-code-review-python.instructions.md` |
| **TypeScript** | `rules/01-typescript.instructions.md` | `rules/18-code-review-typescript.instructions.md` |
| **Rust** | `rules/09-rust.instructions.md` | `rules/19-code-review-rust.instructions.md` |
| **Go** | `rules/11-go.instructions.md` | `rules/20-code-review-go.instructions.md` |
| **Dart** | `rules/08-dart.instructions.md` | `rules/21-code-review-dart.instructions.md` |

## 审查原则

**正确性 > 风格** → **安全红线不放过** → **尊重作者，批评代码** → **每个问题附证据** → **分轻重缓急** → **建议可操作** → **结合上下文**

## 链路 (Chain)

```
code-review → workflow(审查报告)
```

完成后将审查报告交给 `workflow`，由 workflow 按问题类型调度修复、简化或架构评审。
