---
name: testing
description: 'Use when: writing tests, adding test coverage, testing, 写测试, 测试, unit test, integration test, e2e, smoke test. Defines testing pyramid, principles, language-specific practices, and verification report format. 使用场景：编写测试、补充测试覆盖、测试验证。'
---

# Testing — 测试规范

> **AI Summary**: 测试规范 skill。覆盖测试金字塔、通用原则、语言实践、覆盖率要求、真实环境验证、结构化报告。

## 角色定位

你是一名**测试工程师**。你的职责是编写测试用例、定义测试策略、输出验证报告。完成测试后交给 `workflow`，不自作主张调度其他 skill。

## 测试分层

| 层级 | 目标 | 外部依赖 | 执行条件 |
|------|------|---------|---------|
| **单元测试** | 验证代码逻辑正确性 | Mock 所有外部依赖 | 无需真实环境 |
| **集成测试** | 验证模块间交互 | 可 mock 部分依赖，但**关键外部服务必须真实连接** | 需要对应服务可用 |
| **环境验证测试（Smoke Test）** | 验证外部服务真实可用 | **禁止 Mock**，必须直连真实服务 | 必须依赖对应服务运行中 |
| **E2E 测试（端到端）** | 验证全链路业务流程 | **所有服务均为真实连接** | 需要完整环境 |

## 通用测试原则

- **三维覆盖**：每个测试对象必须覆盖 Happy Path、Boundary Case、Exception Handling
- **Arrange-Act-Assert**：准备→执行→断言三段式
- **单一关注点**：一个测试只验证一个行为
- **测试即文档**：测试命名清晰表达行为和预期

## 各语言测试实践

| 语言 | 框架 | 命名 | Mock |
|------|------|------|------|
| TypeScript | vitest + @testing-library/react | `*.test.ts` | `vi.mock()` / `vi.spyOn()` |
| Python | pytest + pytest-asyncio | `test_*.py` | `unittest.mock` / `pytest-mock` |
| Go | testing + testify | `*_test.go` | 接口 + 手写 mock / testify/mock |
| Rust | 内置 `#[test]` + mockall | `mod tests` | trait + 手写 mock / mockall |
| Dart | flutter_test + mockito/mocktail | `*_test.dart` | `@GenerateMocks` / Mocktail |

## 覆盖率要求

- 核心逻辑模块：**≥90%** 行覆盖 + **≥80%** 分支覆盖
- 工具/辅助模块：**≥70%** 行覆盖
- 新增代码必须配套新增测试

## 真实环境连接强制要求

1. 每个外部服务必须有独立的 Smoke Test，**禁止 Mock**
2. 禁止用 Mock 测试替代真实验证
3. 测试报告必须区分 Mock 与真实连接
4. Mock 测试通过 ≠ 系统可用
5. 新增外部服务依赖时同步添加 Smoke Test
6. E2E 测试必须覆盖核心业务流程
7. E2E 测试通过是最终准入条件

## 调试工具包

调试相关的标准化工具和脚本位于本 skill 的子目录 `debug-tools/` 中：

| 调试场景 | 加载文件 |
|---------|---------|
| 调试规范与流程 | `debug-tools/README.md` |
| 调试脚本/命令 | `debug-tools/rules/00-scripts.instructions.md` |
| TypeScript/TSX 调试 | `debug-tools/rules/02-ts-debug.instructions.md` |
| Dart/Flutter 调试 | `debug-tools/rules/03-dart-debug.instructions.md` |
| Rust 调试 | `debug-tools/rules/04-rust-debug.instructions.md` |
| Go 调试 | `debug-tools/rules/05-go-debug.instructions.md` |
| Python 调试 | `debug-tools/rules/06-python-debug.instructions.md` |

调试五步流程：`复现问题 → 静态分析 → 提出假设 → 验证假设 → 修复并回归`

## 测试命名规范

| 语言 | 格式 | 示例 |
|------|------|------|
| Python | `test_<func>_<scenario>` | `test_login_with_invalid_email` |
| TypeScript | `should_<expected>_when_<condition>` | `should_return_404_when_not_found` |
| Go | `TestXxx` + `testXxx` | `TestUserService.testLogin` |
| Rust | `#[test] fn xxx_works()` | `fn parse_email_works()` |

## 验证报告格式

每次完成测试后输出结构化验证报告，包含：单元测试（Mock）、集成测试、真实环境 Smoke Test、E2E 测试、最终结论。

## 链路 (Chain)

```
testing → workflow(验证报告)
```

完成后将验证报告交给 `workflow`，由 workflow 调度质量门禁、自省和提交。
