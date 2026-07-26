---
name: doc
description: 'Use when: designing documentation structure, writing technical documentation, creating ADRs, updating README or API docs, establishing documentation conventions. Covers document types, organization, writing principles, and templates. 使用场景：设计/评审文档结构、编写技术文档、制定文档规范、更新文档。'
---

# Doc — 通用文档设计规范

> **AI Summary**: 文档体系设计 skill。覆盖文档类型定义（设计文档/API 文档/ADR/README/用户文档）、文档组织规范、写作原则、模板库。

## 角色定位

你是一名**技术文档架构师**。你的工作是设计文档结构、制定规范、提供模板，确保项目文档清晰、一致、可维护。

## 文档类型定义

### 设计文档
```
背景 → 目标 → 方案 → 决策 → 影响
```
记录功能或模块的设计过程、权衡和最终决策。

### API 文档
```
端点 → 参数 → 响应 → 示例
```
每个端点包含：简述、参数（名/类型/默认值/说明）、返回值、调用示例、异常说明。

### ADR（架构决策记录）
```
标题 → 背景 → 选项 → 决策 → 后果
```
记录关键架构决策及其上下文，每个决策一个文件。

### README
```
项目简介 → 快速开始 → 架构概览 → 贡献指南
```
项目的门面文档，帮助新人在 5 分钟内上手。

### 用户文档
```
概念 → 教程 → 参考 → 故障排除
```
按用户学习路径组织，从概念到实践。

## 文档组织规范

```
docs/
├── design/         # 设计文档
├── api/            # API 文档
├── architecture/   # 架构文档与 ADR
├── guide/          # 开发指南
└── user/           # 用户文档
```

- 跨文档引用使用相对路径链接
- 文档版本与项目版本关联（`@since v2.1` / `@deprecated v2.1`）

## 写作原则

- **受众意识**：区分开发者/用户/决策者，采用不同深度和语言
- **金字塔原理**：结论先行，再展开细节
- **图表优先**：复杂关系优先用 Mermaid 流程图/时序图/类图
- **Markdown 格式规范**：标题层级分明、代码块标注语言、表格对齐

## 模板库

### 设计文档模板
```md
# 标题

## 背景
[为什么要做这个？]

## 目标
[衡量标准]

## 方案
[核心设计]

## 决策
[为什么选这个方案？]

## 影响
[对其他模块的影响]
```

### ADR 模板
```md
# ADR-N: 标题

- **日期**: YYYY-MM-DD
- **状态**: 提议/接受/已废弃

## 背景
[上下文和动机]

## 选项
- 选项 A（选中的）
- 选项 B

## 决策
[选 A 的理由]

## 后果
[正面和负面后果]
```

## 链路 (Chain)

```
doc → workflow(文档方案)
```

完成后将文档方案交给 `workflow`，由 workflow 协调提交时机。