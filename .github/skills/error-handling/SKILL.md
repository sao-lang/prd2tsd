---
name: error-handling
description: 'Use when: designing error handling architecture, defining error types, implementing exception handling, planning degradation strategy. Covers error classification, propagation strategy, graceful degradation, production logging. 使用场景：设计错误处理架构、定义错误类型、实现异常处理逻辑、优雅降级。'
---

# Error Handling — 统一错误处理规范

> **AI Summary**: 错误处理架构。错误分类(业务/系统/第三方)、传播策略、优雅降级、生产日志。

## 角色定位

你是一名**错误处理架构师**。你的职责是设计错误分类体系、定义传播策略、规划降级方案。完成方案后交给 `workflow`，不自作主张调度其他 skill。

## 核心原则

- **尽早失败**：错误在最接近源头的地方被捕获
- **不吞错误**：禁止空 `catch` / `except: pass`
- **分类处理**：业务错误、系统错误、第三方错误分开
- **信息分层**：用户看到的 != 日志记录的

## 错误分类

| 类型 | 例 | 用户看到 | 日志 |
|------|----|---------|------|
| 业务错误 | 余额不足、参数校验失败 | 友好提示 + 错误码 | 记录操作上下文 |
| 系统错误 | 数据库断连、OOM | 503 / "系统繁忙" | 完整堆栈 + 请求 ID |
| 第三方错误 | 支付超时、API 限流 | "稍后重试" | 记录上游响应 + 降级策略 |

## 传播策略

- **内部函数**：向上传播，不处理
- **模块边界**：转换 + 包装，带上文（`fmt.Errorf("get user %d: %w", id, err)`）
- **API 边界**：捕获 + 转标准响应格式
- **全局兜底**：全局异常中间件作为最后防线

## 优雅降级

```
正常 → 依赖挂了 → 缓存兜底 → 默认值 → 功能降级 → 返回部分数据
```

每步失败就尝试下一步，不直接崩溃。

## 各语言错误处理模式

| 语言 | 模式 | 示例 |
|------|------|------|
| **Python** | 自定义异常继承 `Exception`，BaseException 兜底 | `class BizError(Exception): ...` |
| **TypeScript** | 自定义 Error 子类 + `try/catch` 类型守卫 | `class BizError extends Error { code: string }` |
| **Go** | 哨兵错误 `var ErrX = errors.New(...)` + `%w` 包装 | `fmt.Errorf("get user %d: %w", id, ErrNotFound)` |
| **Rust** | `thiserror` 定义错误类型 + `anyhow` 传播 | `#[derive(thiserror::Error)] enum MyError { ... }` |
| **Dart** | 自定义 Exception 子类，区分 Exception 与 Error | `class BizException implements Exception { ... }` |

## 重试模式

| 场景 | 策略 |
|------|------|
| 网络抖动 | 指数退避 + 随机 jitter，最多 3 次 |
| 数据库死锁 | 自动重试（ORM 内置）+ 最多 3 次 |
| 限流 429 | 读取 `Retry-After` 头，等待后重试 |
| 幂等操作 | 可以安全重试，非幂等操作不重试 |

## 生产日志规范

- 结构化 JSON 格式
- 级别准确：ERROR(需介入) > WARN(异常但可控) > INFO(关键事件) > DEBUG(开发)
- 必含：timestamp, level, module, message, request_id
- 脱敏：password, token, id_card 等不记入日志

## 审查清单

```
□ 错误分类：区分业务/系统/第三方错误
□ 不吞错误：没有空 catch / except: pass
□ 传播策略：边界处转换 + 包装上下文
□ 全局兜底：有全局异常中间件
□ 降级策略：关键依赖挂了有缓存/默认值
□ 日志规范：结构化 + 级别准确 + 脱敏
□ 重试策略：网络抖动有指数退避
□ 测试覆盖：每个错误路径有测试用例
```

## 链路 (Chain)

```
error-handling → workflow(错误处理方案)
```

完成后将错误处理方案交给 `workflow`，由 workflow 调度编码和测试。
