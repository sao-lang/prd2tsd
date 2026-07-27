# Copilot 指令

##  Skill 加载要求

| Skill | 路径 | 加载时机 |
|-------|------|---------|
| **`ai-coding-rules`** 🧠 | `.github/skills/ai-coding-rules/SKILL.md` | **任何开发任务必载**（编码/重构/修复/测试/文档/调试），自动按任务类型选规则文件。调试任务额外加载 `debug-tools` |
| **`grill-me`** 🔥 | `.github/skills/grill-me/SKILL.md` | **始终加载**。触发："拷问我/grill me/自省/self-review/拷问自己"等；复杂任务完成自动触发自省 |
| **`git`** 📝 | `.github/skills/git/SKILL.md` | git 操作（提交/推送/rebase/merge 等） |
| **`code-review`** 🔍 | `.github/skills/code-review/SKILL.md` | 用户要求代码审查/评审/审计时加载。自动关联 `ai-coding-rules` 作为审查标准 |
| **`simplify`** ✂️ | `.github/skills/simplify/SKILL.md` | 用户要求简化代码/去重/降复杂度时加载。自动关联 `ai-coding-rules/rules/06-refactor.instructions.md` |

## 文档约束

设计文档 → `docs/` | 开发记录 → `overview.md` | 自省记录 → `grill-self-review.md`

## 🚨 铁的纪律（违反将导致严重后果）

**纪律一（修改授权）：** 在修改任何文件之前，必须按照`.github\skills\ai-coding-rules\rules\00-base.instructions.md`中的**R8**、**R8b**两条处理，用户的问题描述不算授权。

**纪律二（审查质量）：** 执行 `code-review` 时，必须按照 `code-review/SKILL.md` 第二步「逐层审查」中**「审查操作（必须执行）」列的每一条操作指令**逐条执行，不得跳过任何维度。审查报告末尾必须附「历史漏检覆盖」表格。违反此纪律的审查报告视为无效。