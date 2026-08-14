# Copilot 指令

## Skill 加载要求

> 本仓库即技能集本身，路径均相对仓库根目录。使用方式二选一：直接以本目录作为技能根目录；或在项目中建 `.agents/skills` 软链接指向本目录（Codex 会按 `$REPO_ROOT/.agents/skills` 自动发现）。

| Skill | 路径 | 加载时机 |
|-------|------|---------|
| **`ai-coding-rules`** 🧠 | `ai-coding-rules/SKILL.md` | **任何开发任务必载**（编码/重构/修复/测试/文档/调试），自动按任务类型选规则文件。调试任务额外加载 `debug-tools` |
| **`debug-tools`** 🛠️ | `ai-coding-rules/debug-tools/SKILL.md` | 调试任务（运行时/静态分析排查）额外加载，与 `ai-coding-rules` 搭配 |
| **`grill-me`** 🔥 | `grill-me/SKILL.md` | **始终加载**。触发："拷问我/grill me/自省/self-review/拷问自己"等；复杂任务完成自动触发自省 |
| **`git`** 📝 | `git/SKILL.md` | git 操作（提交/推送/rebase/merge 等） |
| **`code-review`** 🔍 | `code-review/SKILL.md` | 用户要求代码审查/评审/审计时加载。自动关联 `ai-coding-rules` 作为审查标准 |
| **`simplify`** ✂️ | `simplify/SKILL.md` | 用户要求简化代码/去重/降复杂度时加载。自动关联 `ai-coding-rules/rules/06-refactor.instructions.md` |

## 文档约束

设计文档 → `docs/` | 开发记录 → `overview.md` | 自省记录 → `grill-self-review.md`

## 🚨 铁的纪律（违反将导致严重后果）

在修改任何文件之前，必须按照`ai-coding-rules/rules/00-base.instructions.md`中的**R8**、**R8b**两条处理，用户的问题描述不算授权。
