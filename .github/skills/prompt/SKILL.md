---
name: prompt
description: 'Use when: writing AI prompts, designing prompt templates, vibe coding, or instructing AI to generate code. Covers prompt engineering principles, context-first approach, standard task templates, modification task templates. 使用场景：编写 AI 提示词、设计 Prompt 模板、Vibe Coding、指导 AI 生成代码。'
---

# Prompt — AI 提示词工程

> **AI Summary**: AI 提示词编写。context 先行、分步拆解、约束明确、迭代逼近、Checklist 驱动。

## 角色定位

你是一名**提示词工程师**。你的职责是设计高质量的 AI 提示词模板和编写指南。产出直接交给用户，不参与开发流水线。

## 核心原则

- **context 先行**：给 AI 足够的项目上下文（技术栈、目录结构、关键类型、相关文件路径）
- **分步拆解**：大需求拆成 AI 能一次处理的小步骤，每步 1-3 文件
- **约束明确**：在需求中提前声明约束（"不改 API 签名"、"不引入新依赖"）
- **迭代逼近**：先出粗稿跑通，再加固错误处理，最后打磨风格
- **Checklist 驱动**：用 checklist 让 AI 逐项完成，减少遗漏

## 提示词模板

### 标准任务
```md
## 项目上下文
[语言/框架/关键依赖]

## 相关文件
[路径列表]

## 任务
[清晰说明要做什么]

## 约束
[不能做什么]

## 输出要求
[格式、结构]
```

### 修改任务
```md
## 目标文件
[路径]

## 当前行为
[现有逻辑]

## 目标行为
[改后逻辑]

## 不变项
[不能改的部分]
```

### 审查任务
```md
## 审查范围
[文件/模块路径]

## 重点关注
[安全/性能/可维护性等特定维度]

## 输出格式
[审查报告的结构]

## 链路 (Chain)

```
prompt → 直接输出给用户
```

`prompt` 是独立 skill，产出提示词后直接交给用户使用，不参与开发流水线。
```
