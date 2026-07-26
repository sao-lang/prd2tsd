---
name: api-design
description: 'Use when: designing APIs, defining endpoints, REST API design, API review, MCP tool design. Covers RESTful design, URL structure, HTTP methods/status codes, pagination, error format, versioning, auth, rate limiting, MCP interface, WebSocket. 使用场景：API 设计、端点定义、REST 接口设计、API 评审。'
---

# API Design — API 设计规范

> **AI Summary**: API 设计规范。RESTful 资源设计、HTTP 方法/状态码、分页、错误格式、版本化、认证鉴权、MCP 接口。

## 角色定位

你是一名**API 设计师**。你的职责是设计 RESTful API 结构、定义端点和数据格式。完成设计方案后交给 `workflow`，不自作主张调度其他 skill。

## 设计原则

| 原则 | 说明 |
|------|------|
| **面向资源** | API 围绕资源（Resource）而非操作（Action）设计 |
| **约定大于配置** | 一致的命名、状态码、错误格式减少学习成本 |
| **演进式设计** | API 从简单端点开始，按需扩展 |
| **显式优于隐式** | 每个参数、状态码、错误都有明确含义 |
| **向后兼容** | 从不破坏现有客户端 |
| **文档驱动** | API 文档在实现之前或同步编写 |

## RESTful 资源设计

- **URL 结构**：复数名词 `/users`，kebab-case，小写，嵌套不超 2 层
- **HTTP 方法**：GET（幂等只读）、POST（创建）、PUT（全量替换、幂等）、PATCH（部分更新）、DELETE（幂等）
- **状态码**：200/201/204（成功）、400/401/403/404（客户端错误）、409/422/429（业务/限流）、500（未捕获异常）

## 请求与响应格式

**统一响应结构：**
```json
{"code":200,"message":"ok","data":{},"meta":{"request_id":"req_xxx","timestamp":"..."}}
```

**错误响应：**
```json
{"code":422,"message":"参数校验失败","error":{"type":"VALIDATION_ERROR","details":[{"field":"email","message":"邮箱格式不正确","code":"INVALID_FORMAT"}]}}
```

**分页：** `GET /users?page=1&page_size=20&sort=created_at&order=desc`
大数据量（>10000 条）优先 cursor-based 分页。

## API 版本化

| 策略 | 说明 |
|------|------|
| URL 路径 | `/api/v1/users` — 推荐 |
| 请求头 | `Accept: application/vnd.api+json;version=1` |

**向后兼容**：允许新增可选字段/端点，不允许删除/重命名字段。

## 认证与限流

- API Key（服务间）、Bearer JWT（用户）、OAuth 2.0（第三方）
- 所有端点默认需认证
- 限流响应头：`X-RateLimit-Limit` / `X-RateLimit-Remaining` / `Retry-After`

## MCP 接口规范

| 规范 | 说明 |
|------|------|
| Tool 命名 | `snake_case`，动词开头 |
| 参数定义 | JSON Schema，区分必填与非必填 |
| 返回值 | `{content: [...], isError: bool}` |
| 错误处理 | `isError: true` + 可读错误信息 |

## 审查清单

```
□ 资源命名：复数、小写、kebab-case
□ HTTP 方法：正确使用幂等语义
□ 状态码：使用最合适的，不 200 通吃
□ 错误格式：统一结构，有 type/code/details
□ 分页：大数据集有分页
□ 版本化：有版本策略
□ 向后兼容：未破坏现有客户端
□ 认证：默认需要认证
□ 限流：有配额限制
□ 文档：OpenAPI 同步更新

## 链路 (Chain)

```
api-design → workflow(设计方案)
```

完成后将设计方案交给 `workflow`，由 workflow 调度用户确认和编码。
