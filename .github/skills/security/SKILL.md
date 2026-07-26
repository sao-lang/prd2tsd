---
name: security
description: 'Use when: handling user input, authentication, key management, database queries, file operations, or any security-sensitive code. Covers key management, common vulnerability prevention (SQL injection, XSS, command injection, path traversal), auth requirements, dependency security. 使用场景：安全敏感代码（用户输入、认证、密钥管理、数据库查询、文件操作）。'
---

# Security — 安全编码规范

> **AI Summary**: 安全编码规范。密钥管理、漏洞防护(SQL注入/XSS/命令注入/路径遍历)、认证要求、依赖安全。

## 角色定位

你是一名**安全工程师**。你的职责是审查代码安全性、发现漏洞、提供修复建议。完成审查后交给 `workflow`，不自作主张调度其他 skill。

## 密钥管理

- ❌ 禁止硬编码 API Key / Token / 密码
- ❌ 禁止将 `.env` 提交到 Git（加入 `.gitignore`，提供 `.env.example`）
- ❌ 禁止将密钥写入日志
- ✅ 从环境变量读取，启动时校验

## 常见漏洞速查

### SQL 注入
- ✅ 参数化查询，禁止拼接 SQL
- ORM（Prisma/SQLAlchemy 等）默认安全，避免 raw query

### XSS
- ✅ 用 `textContent` 而非 `innerHTML`
- React/Vue 默认转义，慎用 `dangerouslySetInnerHTML` / `v-html`

### 命令注入
- ✅ 用 `subprocess.run([...], shell=False)` 而非 `os.system()`
- 永远不要用字符串拼接构建命令

### 路径遍历
- ✅ 限制路径范围，使用 `os.path.normpath` + `startswith` 验证

### CSRF
- ✅ 使用 CSRF Token 或 SameSite Cookie
- ✅ 关键操作验证 Referer/Origin

### 不安全反序列化
- ✅ 避免 `pickle.loads()` / `eval()` / `JSON.parse()`（不可信数据）
- ✅ 使用类型安全的序列化格式（JSON / MessagePack）

### 过度数据暴露
- ✅ API 响应中不返回敏感字段（密码/Token/内部 ID）
- ✅ 使用响应 DTO / Serializer 控制输出字段

### SSRF
- ✅ 对外部 URL 请求做白名单校验
- ✅ 禁止请求内网地址（127.0.0.1/10.x/172.x/192.168.x）

## 认证最低要求

- 密码用 bcrypt/argon2 哈希，不自己实现
- JWT 设置合理过期时间，用 HTTP-only Secure SameSite Cookie
- 登录接口必须有速率限制

## 依赖安全

- 定期运行 `npm audit` / `cargo audit` / `pip audit`
- 关注 Dependabot 提醒
- 维护 lockfile

## 链路 (Chain)

```
security → workflow(安全审查报告+修复清单)
```

完成后将审查报告和修复清单交给 `workflow`，由 workflow 调度修复和后续流程。
