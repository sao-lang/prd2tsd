---
name: git
description: 'Use when: committing code, writing commit messages, pushing, or any git operation. 使用场景：代码提交、编写提交信息、推送、git 操作。'
user-invocable: true
---

# Git 操作规范

> **AI Summary**: Git 操作规范。提交信息格式、原子提交、分支策略、冲突处理、推送策略。

## 角色定位

你是一名**版本控制操作员**。你的职责是执行 git 操作：提交、推送、分支管理。由 `workflow` 调用，执行完即闭环终点。

## 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

| 部分 | 必填 | 说明 |
|------|------|------|
| `type` | ✅ | feat / fix / refactor / perf / test / docs / style / chore / ci / revert |
| `scope` | ❌ | 影响模块 |
| `subject` | ✅ | ≤72 字符，首字母小写，无句号 |
| `body` | ❌ | 写动机（why），不写内容（what） |
| `footer` | ❌ | BREAKING CHANGE、Closes #issue |

## 原子提交

- 每次提交只做一件事
- 改了 3 个不相关的文件 → 拆 3 次提交
- subject 用动词开头（增加/修复/重构/优化）

## 推送策略

- 推送前 `git pull --rebase`
- 已推送公共分支用 `git revert` 回退
- 本地分支用 `git reset`
- 合并优先 `--no-ff`

## 分支策略

| 分支 | 用途 | 来源 | 合并目标 |
|------|------|------|---------|
| `main` | 生产就绪代码 | `develop` | — |
| `develop` | 集成分支 | 功能分支 | `main` |
| `feat/*` | 新功能 | `develop` | `develop` |
| `fix/*` | Bug 修复 | `develop`/`main` | `develop`/`main` |
| `release/*` | 发布准备 | `develop` | `main` + `develop` |
| `hotfix/*` | 紧急修复 | `main` | `main` + `develop` |

## 合并策略

- 功能分支 → develop：**Squash merge**（保持 develop 历史干净）
- develop → main：**Merge commit** `--no-ff`（保留发布节点）
- hotfix → main：**Merge commit** `--no-ff`（标记紧急修复）

## 冲突处理

1. `git merge --abort` 无法解决时重置
2. 手动编辑冲突文件，搜索 `<<<<<<<` `=======` `>>>>>>>`
3. 确认保留正确代码，删除冲突标记
4. `git add` → `git commit`（无 `-m`，使用默认合并信息）
5. 解决后运行测试确认不破坏功能

## 交互式 rebase 常用操作

| 命令 | 用途 |
|------|------|
| `pick` | 保留该 commit |
| `reword` | 修改 commit message |
| `squash` | 合并到上一个 commit |
| `fixup` | 合并到上一个，丢弃 message |
| `drop` | 删除该 commit |
| `edit` | 暂停 rebase 修改内容 |

> 交互式 rebase 仅用于**尚未推送**的本地 commit。已推送的 commit 用 `git revert`。

## 链路 (Chain)

```
git ← workflow(变更文件列表+提交信息模板)
  → 执行提交 → 完成(闭环终点)
```

`git` 是流水线的**最后一个环节**。由 `workflow` 调用，执行完提交后整个任务闭环完成。
