# Copilot 指令

## Skill 加载要求

### 1. `ai-coding-rules` — 开发任务必载

进行**任何开发任务**（编码、重构、修复、测试、文档、调试、代码提交等）时，**必须优先加载 `ai-coding-rules` skill**：

> `.github/skills/ai-coding-rules/SKILL.md`

该 skill 会根据任务类型自动选择对应的规则文件（如 Python 规则、TypeScript 规则、重构规则等），确保行为与项目约定一致。

> **调试任务**：加载 `ai-coding-rules` 的同时，**必须额外加载 `debug-tools` skill**（见下文第 3 条）。`ai-coding-rules` 提供编码约束，`debug-principles` skill 提供通用调试原则，`debug-tools` 提供标准化脚本和语言专项调试流程。

### 2. `grill-me` — 拷问模式必载

**始终加载 `grill-me` skill**，保持就绪状态。当用户说出"拷问我"、"grill me"、"盘问"、"面试我"、"考考我"、"challenge me"、"interrogate"等触发词时，立即激活 Socratic 拷问者人格：

> `.github/skills/grill-me/SKILL.md`

#### 复杂任务后自动自省

完成**复杂任务**（修改 ≥3 文件、涉及架构设计/系统决策/安全策略/API 设计/多步骤推理链等）后，**必须自动触发 `grill-me` 的模式三（任务后自动自省）**：

1. 完成用户需求的实现
2. 按 grill-me 的复杂任务判定标准判断当前任务是否触发自省
3. 如果触发，按四大维度逐项检查：
   - **功能完整性** — 所有功能点都完成了吗？
   - **功能间联通** — 功能之间数据流/调用链通了吗？
   - **模块间联通** — 新模块与现有模块接口兼容吗？
   - **可用性** — 能实际运行吗？有严重 bug 吗？
4. 输出精简自省报告
5. 发现严重问题（功能遗漏/联通断点/运行时错误/安全漏洞/破坏现有功能）时，**不等用户指示，主动修复**，修复后二次自省

> 简单任务（typo、重命名、纯问答）不触发自省。

### 3. `debug-tools` — 调试排查必载

进行**调试任务**（运行时异常、Bug 定位、性能分析、测试失败排查、构建错误等）时，**必须同时加载 `debug-tools` skill**：

> `.github/skills/debug-tools/SKILL.md`

该 skill 提供标准化的调试脚本（`rules/00-scripts.instructions.md`）、调试规范与禁止事项（`rules/01-rules.instructions.md`），以及各语言的专项调试规则：

| 语言 | 调试规则文件 |
|------|-------------|
| Python | `rules/06-python-debug.instructions.md` |
| TypeScript/TSX | `rules/02-ts-debug.instructions.md` |
| Dart/Flutter | `rules/03-dart-debug.instructions.md` |
| Rust | `rules/04-rust-debug.instructions.md` |
| Go | `rules/05-go-debug.instructions.md` |

使用原则：
- **静态分析优先**：先阅读源码、追踪数据流、分析类型，再使用运行时工具
- **脚本工具辅助**：使用标准化脚本快速收集证据，避免手工重复操作
- **规则约束兜底**：不盲改、不掩盖、不留调试代码
- **根因修复**：定位根本原因而非表面症状，修复后补充测试用例

### 4. `refactor-rules` — 重构必载

进行**重构/架构变更/跨模块修改/新增大型功能**时，**必须加载 `refactor-rules` skill**：

> `.github/skills/refactor-rules/SKILL.md`

提供 3 步重构工作流：改前分析（5 项）→ 完整源码交付 → 改后总结。重构不得改变外部行为。

### 5. `commit-rules` — 提交必载

进行**Git 提交/推送/版本管理**时，**必须加载 `commit-rules` skill**：

> `.github/skills/commit-rules/SKILL.md`

提供 Conventional Commits 规范、原子提交原则、推送策略。

### 6. `doc-rules` — 文档更新必载

进行**文档编写/更新/审查**时，**必须加载 `doc-rules` skill**：

> `.github/skills/doc-rules/SKILL.md`

提供文档同步原则、API 文档规范、Markdown 风格指南。改代码必查文档。

### 7. `debug-principles` — 调试原则必载

进行**调试任务**时，**必须同时加载 `debug-principles` skill**（与 `debug-tools` 互补）：

> `.github/skills/debug-principles/SKILL.md`

提供 5 步调试流程、日志/断点规范、禁止事项（不盲改/不掩盖/不留调试代码）。`debug-tools` 提供标准化脚本和语言专有命令。