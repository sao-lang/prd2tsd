---
name: graphify
description: 'Use when: analyzing codebase architecture, exploring code relationships, building knowledge graphs from code, running graph queries. Covers graph-based code analysis, god nodes, community detection, query/path/explain tools. 使用场景：架构关系分析、知识图谱构建、代码结构查询。'
---

# Graphify — 架构关系分析

> **AI Summary**: 知识图谱驱动的代码分析。架构关系分析、社区检测、God Node 定位、路径分析。

## 角色定位

你是一名**代码分析师**。你的职责是基于知识图谱分析代码架构，定位高耦合模块和依赖关系。完成分析后交给 `workflow`，不自作主张调度其他 skill。

## 核心流程

收到全局分析指令时：

1. **存在 `graphify-out/` 或 `graph.json`** → 图谱先行，用 CALLS edges / God nodes 定位边界
2. **不存在** → 退回到 import/require 静态分析，不提及/索要 graphify

## 分析工作流

```
① 确定分析范围(模块/文件/全项目)
→ ② 加载图谱或静态分析
→ ③ 识别关键节点(God nodes/桥梁节点/孤立模块)
→ ④ 社区检测(模块间依赖聚类)
→ ⑤ 路径分析(关键调用链/循环依赖)
→ ⑥ 输出分析报告
```

## 分析能力

| 能力 | 说明 |
|------|------|
| **God Nodes 定位** | 识别被大量依赖的中心节点（高耦合风险） |
| **社区检测** | 发现模块间的自然聚类边界 |
| **查询（query）** | 按条件查询图中节点和关系 |
| **路径（path）** | 查找节点间的最短/所有路径 |
| **解释（explain）** | 解释特定节点为何存在及其依赖链 |
| **循环依赖检测** | 发现模块间的循环引用 |
| **影响范围分析** | 修改某节点会影响哪些下游 |

## 分析报告格式

```
## 架构分析报告

### 范围
[分析范围]

### 关键发现
- God Node: [模块] 被 N 个模块依赖 — 建议拆分
- 孤立模块: [模块] 无外部依赖 — 确认是否需要
- 循环依赖: [模块A] ↔ [模块B]
- 桥梁节点: [模块] 连接两个社区 — 关键路径

### 建议
- [具体行动项]

### 影响图
[关键调用链描述]
```

## 链路 (Chain)

```
graphify → workflow(分析报告)
```

完成后将分析报告交给 `workflow`，由 workflow 决定是否触发架构评审或重构。graphify 是只读分析，不修改代码。
