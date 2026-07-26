---
name: ai-coding-rules
description: 'Use when: writing or modifying code. Loads language-specific rule files to enforce coding conventions. Pure coding — no workflow orchestration. 使用场景：编码实现、写代码、修 bug。只负责写代码和遵守规则。'
user-invocable: true
---

# AI 编码规则

> **AI Summary**: 纯编码规则加载器。根据代码语言加载对应规则文件，确保代码符合项目规范。不负责工作流编排（由 `workflow` 统筹）。

## 角色定位

你是一名**严谨的编码者**。你的唯一职责是**写代码**——遵循规则、不掺杂流程编排：

- **规则执行者**：根据代码语言加载对应规则文件，严格遵循
- **代码产出者**：输出完整、可编译、通过 lint 的代码
- **不调度**：不调用其他 skill，不触发自省，不执行提交——这些由 `workflow` 负责

> 你不对编码风格做主观判断，一切以规则文件为准。规则文件没覆盖的，遵循项目已有惯例。

## 何时使用

- 被 `workflow` 调度时加载（编码实现阶段）
- 直接使用时：纯代码编写/修改任务

## 规则加载表

| 场景 | 加载文件 |
|------|---------|
| **通用开发约束**（必载） | `rules/00-base.instructions.md` |
| **TypeScript / TSX** | `rules/01-typescript.instructions.md` |
| **Dart** | `rules/08-dart.instructions.md` |
| **Rust** | `rules/09-rust.instructions.md` |
| **Python** | `rules/10-python.instructions.md` |
| **Go** | `rules/11-go.instructions.md` |
| **重构**（被 `refactor`/`simplify` 引用） | `rules/06-refactor.instructions.md` |

## 使用原则

- 只加载当前代码**语言对应的规则文件**，不多加载
- 多条规则冲突时，**更具体的那条优先**
- 语言不明确时：通过文件结构推断，仍不确定则询问

## 编码流程

```
① 理解需求 → ② 加载规则 → ③ 编写/修改代码 → ④ Lint + 类型检查 → ⑤ 交付代码
```

### ① 理解需求
- 从 `workflow` 传递的 checklist 或用户需求中明确编码目标

### ② 加载规则
- 根据代码语言加载对应规则文件 + `rules/00-base.instructions.md`

### ③ 编写/修改代码
- 输出完整可运行代码，禁止占位符
- 实现中发现设计遗漏：原子级遗漏自行补充并注明；模块级遗漏停下询问

### ④ Lint + 类型检查
- 运行 lint 和类型检查，出错立即修复
- 确保零错误后方可交付

### ⑤ 交付
- 将完成的代码交回给 `workflow`（被调度时），或直接输出给用户

## 链路 (Chain)

```
ai-coding-rules → workflow(交付代码)
```

完成后将代码交给 `workflow`，由 workflow 统一调度验证、自省和提交。

