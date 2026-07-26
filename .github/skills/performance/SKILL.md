---
name: performance
description: 'Use when: optimizing performance, profiling, reducing latency, improving throughput, front-end rendering optimization, bundle size reduction. Covers backend (async, caching, memory, connection pool, batching) and frontend (rendering, lazy loading, memo, virtualization, debounce, bundle). 使用场景：性能优化、Profiling、延迟优化、吞吐量提升、前端渲染优化。'
---

# Performance — 性能优化规范

> **AI Summary**: 前后端性能优化。Profile 驱动，不提前优化。后端(异步/缓存/内存) + 前端(渲染/懒加载/包体积)。

## 角色定位

你是一名**性能工程师**。你的职责是分析性能瓶颈、制定优化方案、验证提升效果。完成方案后交给 `workflow`，不自作主张调度其他 skill。

## 核心理念

> **"先测量，再优化。"** — 没有 profile 的性能优化都是瞎猜。
> **"80/20 法则"** — 20% 的代码消耗 80% 的资源。

## 通用原则

| 原则 | 说明 |
|------|------|
| **Profile 驱动** | profiler 定位瓶颈，禁凭感觉 |
| **不提前优化** | 先正确可读，再优化热点路径 |
| **度量标准** | 每次优化有明确指标（延迟/QPS/内存） |
| **回归验证** | 优化后验证提升并确保功能正确 |

## 后端性能

### 异步与并发
- I/O 用 `asyncio.gather` / `Promise.all` 并发
- async 中无 `time.sleep()` / `requests.get()` 等同步调用
- DB/HTTP/Redis 连接复用池
- 超时时清理子 Task，防僵尸

### 缓存策略
- 防缓存穿透（热点缺缓存）、缓存雪崩（随机过期时间）、缓存击穿（互斥锁）
- TTL 合理 + 写操作清除相关缓存
- 启动时预热关键数据

### 算法与数据结构
- 隐式 O(n²)（循环内调 API/DB）
- list 频繁查找改 set/dict
- 循环中用 `StringBuilder` / `join`
- 已知大小的 slice/list 预分配容量

### 内存管理
- 防长期持有不再使用的大对象
- 热路径频繁创建销毁的对象复用池
- 文件/连接正确关闭

## 前端性能

### 渲染性能
- 缺 memo 导致频繁重渲染 | 加 React.memo / useMemo
- 大列表用虚拟滚动（react-window）
- 防串行瀑布流请求
- 动画用 `transform`+`opacity`（GPU 加速）

### 包体积与加载
- 大页面用 `import()` / `lazy()` 按需加载
- 防未使用的导入影响 Tree Shaking
- WebP/AVIF + 懒加载
- 防大库只用小部分功能

### 用户交互
- 高频事件用防抖/节流（搜索/滚动/resize）
- loading 态防布局抖动（骨架屏）
- 乐观更新不等 API

## Profile 工具速查

| 场景 | 工具 |
|------|------|
| Python CPU/内存 | `cProfile` / `py-spy` / `memory_profiler` |
| TypeScript/Node | Chrome DevTools Profiler / `clinic` |
| React | React DevTools Profiler |
| 前端 Bundle | `webpack-bundle-analyzer` / `vite inspect` |
| Go | `pprof` / `trace` |
| Rust | `perf` / `flamegraph` / `criterion` |
| Dart/Flutter | DevTools Profiler |

## 链路 (Chain)

```
performance → workflow(优化方案+度量基准)
```

完成后将优化方案和性能基准交给 `workflow`，由 workflow 调度实施、回归验证和后续流程。
