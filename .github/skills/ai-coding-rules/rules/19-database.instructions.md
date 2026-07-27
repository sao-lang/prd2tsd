---
applyTo: never
---

# Database Rules — 数据库与 ORM 规范

> **AI Summary**: 数据库开发规范。SQLite + ORM（SQLAlchemy 等）→ 连接/查询/索引/事务/N+1 预防。

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

### 模型定义

| 检查项 | 说明 |
|--------|------|
| **类型安全** | 字段类型精确 |
| **索引声明** | 频繁查询字段声明 `index=True` |
| **唯一约束** | 业务唯一字段加约束 |
| **关系定义** | 外键正确定义 `lazy` 策略 |
| **默认值** | 字段有合理默认值 |
| **nullable** | 可空字段明确 `nullable=True` |

### 查询优化

| 检查项 | 说明 |
|--------|------|
| **select 字段** | 防 SELECT * |
| **预加载关系** | 用 `joinedload`/`selectinload`/`prefetch_related` 预加载 |
| **延迟加载陷阱** | 循环中防 N+1 |
| **批量操作** | 逐条改 `bulk_insert`/`bulk_update` |
| **count 优化** | 大表用近似值或缓存 |
| **分页查询** | 大数据量用分页（cursor-based 优先） |

### N+1 查询预防

```python
for user in users: print(user.orders)  # ❌ N+1
users = session.query(User).options(selectinload(User.orders)).all()  # ✅ 预加载
```

| ORM | N+1 预防 |
|-----|---------|
| SQLAlchemy | `joinedload()` / `selectinload()` |
| Django ORM | `select_related()` / `prefetch_related()` |
| Prisma | `include` / `select` 嵌套 |
| TypeORM | `relations` |
| GORM | `Preload("Orders")` |

### 事务管理

| 检查项 | 说明 |
|--------|------|
| **事务边界** | 包裹最小必要操作，不在事务中做耗时 I/O |
| **自动提交** | 防依赖 ORM 自动提交，显式 `commit()` |
| **回滚处理** | 异常时 `session.rollback()` |
| **隔离级别** | 适合当前场景 |
| **长事务** | 不跨越 HTTP 请求或用户交互 |

## SQL 查询规范

| 检查项 | 说明 |
|--------|------|
| **参数化查询** | 用 `?` / `%s`，禁字符串拼接 |
| **SELECT \*** | 只取所需字段 |
| **LIMIT** | 限制返回行数 |
| **WHERE 条件** | 利用索引，避免索引列上使用函数 |
| **EXISTS 优化** | `IN (SELECT)` 大数据集改 `EXISTS` |
| **EXPLAIN** | 慢查询用 `EXPLAIN ANALYZE` |

## 索引设计

| 检查项 | 说明 |
|--------|------|
| **查询驱动** | 基于实际查询模式设计索引 |
| **复合索引顺序** | 等值列在前，范围列在后 |
| **索引覆盖** | 高频查询用覆盖索引满足 |
| **冗余索引** | 检查重复/冗余：`(a,b)` 和 `(a)` |
| **未使用索引** | 是否有建立了但从未使用的索引 |
| **索引维护** | SQLite 定期 `REINDEX` / `ANALYZE` |

## 迁移管理

| 检查项 | 说明 |
|--------|------|
| **版本管理** | 所有 schema 变更通过迁移脚本执行，禁止手动 DDL |
| **可逆性** | 每个迁移有 `upgrade` 和 `downgrade` 路径 |
| **原子性** | 迁移在单个事务中执行 |
| **迁移工具** | Python: Alembic, Go: golang-migrate, Rust: diesel |

## 数据库审查清单

```
□ 连接池：使用了连接池，无连接泄漏
□ WAL 模式：SQLite 开启了 WAL 模式
□ N+1 查询：ORM 查询已预加载关联数据
□ 批量操作：循环内无逐条 insert/update
□ 索引策略：关键查询字段有索引，无冗余索引
□ 参数化查询：所有 SQL 使用参数化，无拼接
□ 分页：大数据量查询有 LIMIT/OFFSET
□ SELECT *：只选取必要字段
□ 事务管理：事务范围最小化，异常时有回滚
□ 迁移管理：schema 变更通过迁移脚本
□ EXPLAIN：慢查询有 EXPLAIN 分析
```
