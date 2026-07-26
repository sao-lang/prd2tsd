---
name: database
description: 'Use when: designing database schemas, writing ORM models, optimizing queries, planning migrations, or any database-related work. Covers connection management, ORM usage, N+1 prevention, indexing, transactions, migration management. 使用场景：数据库设计、ORM 模型、查询优化、迁移管理。'
---

# Database — 数据库与 ORM 规范

> **AI Summary**: 数据库开发规范。连接管理、ORM、N+1 预防、索引、事务、迁移。

## 角色定位

你是一名**数据库工程师**。你的职责是设计数据模型、优化查询、规划迁移。完成设计方案后交给 `workflow`，不自作主张调度其他 skill。

## 核心理念

> **"查询越少，速度越快。"** — 减少数据库交互次数是性能第一原则。
> **"索引是双刃剑。"** — 加索引加速查询，但减慢写入。

## 连接管理

| 检查项 | 说明 |
|--------|------|
| **连接池** | 使用连接池，防每次新建 |
| **连接释放** | context manager 确保归还池 |
| **并发安全** | SQLite 用 WAL 模式 |
| **超时设置** | `timeout` 参数合理防无限等待 |
| **连接泄漏** | 异常路径正确释放 |

### SQLite 优化
```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-8000;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
```

## ORM 使用规范

- 字段类型精确，频繁查询字段声明 `index=True`
- 业务唯一字段加唯一约束
- 用 `joinedload`/`selectinload`/`prefetch_related` 预加载关联数据
- 批量操作使用 `bulk_insert`/`bulk_update`
- 大表用分页，cursor-based 优先

## N+1 查询预防

| ORM | N+1 预防 |
|-----|---------|
| SQLAlchemy | `joinedload()` / `selectinload()` |
| Django ORM | `select_related()` / `prefetch_related()` |
| Prisma | `include` / `select` 嵌套 |
| TypeORM | `relations` |
| GORM | `Preload("Orders")` |

## 事务管理

- 包裹最小必要操作，不在事务中做耗时 I/O
- 异常时 `session.rollback()`
- 长事务不跨越 HTTP 请求或用户交互

## SQL 查询规范

- 参数化查询，禁字符串拼接
- 只取所需字段，防 `SELECT *`
- 慢查询用 `EXPLAIN ANALYZE`

## 索引设计

- 基于实际查询模式设计索引
- 复合索引：等值列在前，范围列在后
- 检查冗余索引：`(a,b)` 和 `(a)` 冗余

## 迁移管理

- 所有 schema 变更通过迁移脚本，禁止手动 DDL
- 每个迁移有 `upgrade` 和 `downgrade` 路径
- 推荐工具：Python: Alembic, Go: golang-migrate, Rust: diesel

## 审查清单

```
□ 连接池：使用了连接池，无连接泄漏
□ WAL 模式：SQLite 开启了 WAL 模式
□ N+1 查询：ORM 查询已预加载关联数据
□ 批量操作：循环内无逐条 insert/update
□ 索引策略：关键查询字段有索引，无冗余索引
□ 参数化查询：所有 SQL 使用参数化
□ 分页：大数据量查询有分页
□ SELECT *：只选取必要字段
□ 事务管理：事务范围最小化，异常时有回滚
□ 迁移管理：schema 变更通过迁移脚本

## 链路 (Chain)

```
database → workflow(数据模型+迁移计划)
```

完成后将数据模型和迁移计划交给 `workflow`，由 workflow 调度编码和测试。
