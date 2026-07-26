---
applyTo: '**/*.{rs}'
---

# Rust Debug Rules

> **AI Summary**: Rust 调试：cargo check→clippy→dbg!→RUST_BACKTRACE→Miri。

策略：**编译器错误优先，单元测试隔离，`dbg!`/`tracing` 打点**。

## 调试脚本

```powershell
# ── 编译检查 ──
cargo check                                    # 编译检查
cargo check --all-targets                      # 含所有 target
cargo build                                    # 完整编译
cargo check 2>&1                               # 完整错误信息

# ── 测试 ──
cargo test                                     # 全部
cargo test test_name                           # 指定名称
cargo test -- --nocapture                      # 显示 stdout
cargo test -- --test-threads=1                 # 单线程

# ── Clippy / 格式化 ──
cargo clippy --all-targets -- -D warnings      # Lint
cargo fmt --check                              # 格式检查
cargo test --doc                               # 文档测试

# ── Release ──
cargo build --release
# Cargo.toml: [profile.release] debug = true  # 保留 debug 符号
```

## 常见问题与排查

### 借用检查器错误

```rust
// 多个可变引用 → RefCell/Mutex 实现内部可变性
// 生命周期不匹配 → 检查标注
// DEBUG: let cloned = value.clone();  // 临时绕过（提交前清理）
```

### 生命周期标注

```rust
fn debug_lifetime<'a, 'b>(x: &'a str, y: &'b str) -> &'a str {
    x  // 报错说明返回引用与 'a 不匹配
}
```

### 所有权问题

```rust
// DEBUG: [function] value moved, remaining=%?
// 考虑 & 引用 / Clone / Copy trait
```

### Panic / 运行时崩溃

```powershell
$env:RUST_BACKTRACE = "1"; cargo run    # 完整回溯
$env:RUST_BACKTRACE = "full"; cargo run # 更详细
```

```rust
let result = panic::catch_unwind(|| { /* 可能 panic */ });
```

### Unsafe 代码

```rust
// 检查：裸指针操作 / FFI ABI / Miri 检测未定义行为
// cargo +nightly miri test
// SAFETY: [说明]
// DEBUG: [function] unsafe block | ptr=%p, len=%d
```

### 并发问题

```rust
// Arc<Mutex<T>> 或 channels 共享状态
// 死锁：检查锁顺序一致、用 TryLock 非阻塞尝试
// DEBUG: [function] lock acquired | thread=%?
// DEBUG: [function] lock released | thread=%
```

### 异步 Rust 问题

```rust
// 检查 Future 是否被 poll（未 .await 的 Future 不会执行）
// 检查 async block 中是否使用了非 Send 类型（多线程运行时要求 Future: Send）
// 检查阻塞操作是否在异步上下文中使用（应改用 tokio::fs、tokio::io 等）

// 打点验证
// DEBUG: [async_fn] start | args=%?
// DEBUG: [async_fn] after await point 1 | state=%?
// DEBUG: [async_fn] complete | result=%?
```

## 调试宏规范

```rust
// 1. dbg! 宏 — 最快捷的运行时打印（自动包含文件、行号、表达式和值）
// 注意：dbg! 在 release 模式下也会存在（除非用 cfg(debug_assertions) 包裹）
// DEBUG:
let value = dbg!(some_expression);

// 2. 条件编译调试日志（生产代码中推荐方式）
#[cfg(debug_assertions)]
{
    // DEBUG: [function] debug info | val=%?
}

// 3. 使用 tracing / log crate
// Cargo.toml 中添加 tracing
// use tracing::{debug, info, warn, error};
// DEBUG: tracing::debug!(target: "my_module", "message: {:?}", value);
```

## 调试构建配置

```toml
# Cargo.toml — 调试优化配置
[profile.dev]
# 默认已有 debug = true
opt-level = 0   # 无优化，保留所有调试信息

[profile.release]
debug = 1       # release 也保留行号信息（用于性能调试）
opt-level = 3   # 完整优化
```

## 调试流程

```
① cargo check → 修复编译错误
② cargo clippy → 修复 lint 警告
③ cargo test → 确认测试通过
④ 运行时使用 RUST_BACKTRACE=full 获取完整回溯
⑤ 用 dbg! 宏打点定位运行时逻辑问题
⑥ unsafe 块用 Miri 检测未定义行为
⑦ 修复后：cargo check + cargo clippy + cargo test 回归验证
```
