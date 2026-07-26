# Debug Tools — 调试工具包

> **说明**：本目录是调试工具包，非独立 skill。由 `testing` skill 按需加载，提供标准化调试脚本和排查流程。

## 规则文件索引

| 任务类型 | 加载文件 |
|---------|---------|
| 调试脚本/命令 | `rules/00-scripts.instructions.md` |
| 调试规范与禁止事项 | `rules/01-rules.instructions.md` |
| TypeScript/TSX 调试 | `rules/02-ts-debug.instructions.md` |
| Dart/Flutter 调试 | `rules/03-dart-debug.instructions.md` |
| Rust 调试 | `rules/04-rust-debug.instructions.md` |
| Go 调试 | `rules/05-go-debug.instructions.md` |
| Python 调试 | `rules/06-python-debug.instructions.md` |
| React 组件调试 | `rules/00-scripts.instructions.md` + `rules/01-rules.instructions.md` |
| 构建/打包调试 | 优先加载 `rules/00-scripts.instructions.md` |

## 调试五步流程

```
① 复现问题 → ② 静态分析 → ③ 提出假设 → ④ 验证假设 → ⑤ 修复并回归
```

## 使用原则

1. **静态分析优先**：先阅读源码再使用运行时工具
2. **脚本工具辅助**：使用标准化脚本快速收集证据
3. **根因修复**：定位根本原因而非表面症状
4. **至少两个证据链**：指向同一根因再下结论

## 日志规范

- 临时调试日志标记 `// DEBUG:` 或 `# DEBUG:` 前缀
- 生产代码禁止 `console.log` / `print`，使用项目 logger
- 避免 token/密码等敏感信息

## 禁止事项

| 编号 | 规则 |
|------|------|
| R-D1 | 未定位根因前不修改代码（不盲改） |
| R-D2 | 禁止用 try-catch 吞错误绕过修复 |
| R-D3 | 临时日志和断点提交前必须清理 |
| R-D4 | 不确定的 API 查文档 |
| R-D5 | 修复后确认根因已消除 |
| R-D6 | 至少两个证据链指向同一根因 |
| R-D7 | 失败操作分析原因后再决定下一步 |

## 调试报告格式

```
## 调试报告

### 问题描述
[触发条件 | 预期行为 | 实际行为]

### 排查过程
1. [步骤 + 发现]

### 根因分析
[根本原因]

### 修复方案
[修改文件、改动内容、预期效果]

### 防护措施
[新增测试、类型完善等]
```
