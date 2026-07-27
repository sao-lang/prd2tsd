---
name: git
description: 'Use when: committing code, writing commit messages, pushing, or any git operation. 使用场景：代码提交、编写提交信息、推送、git 操作。'
user-invocable: true
---

# Git 操作规范

> 当需要提交代码、编写提交信息、推送或执行 git 操作时加载。

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
