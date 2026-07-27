---
applyTo: never
---

# Performance Rules — 性能优化规范

> **AI Summary**: 前后端性能优化规范。覆盖后端（profiling、async、缓存、内存、连接池、批处理）和前端（渲染优化、懒加载、memo、虚拟化、防抖节流、包体积）两大场景。

## 核心理念

> **"先测量，再优化。"** 没有 profile 的性能优化都是瞎猜。
> **"80/20 法则"**：20% 的代码消耗 80% 的资源——找到那 20%。

## 通用原则

| 原则 | 说明 |
|------|------|
| **Profile 驱动** | profiler 定位瓶颈，禁凭感觉 |
| **不提前优化** | 先正确可读，再优化热点路径 |
| **度量标准** | 每次优化有明确指标（延迟/QPS/内存） |
| **回归验证** | 优化后验证提升，功能正确 |
| **最慢路径优先** | 优化链路最慢环节，非最易环节 |

---

## 后端性能

### 异步与并发

| 检查项 | 说明 |
|--------|------|
| **并发执行** | I/O 用 `asyncio.gather` / `Promise.all` 并发 |
| **同步阻塞** | async 中无 `time.sleep()` / `requests.get()` 等同步调用 |
| **连接池** | DB/HTTP/Redis 连接复用池 |
| **线程池** | CPU 密集托给 `loop.run_in_executor` |
| **Task 取消** | 超时时清理子 Task，防僵尸 |
| **锁粒度** | 最小化持有时间，读多写少用读写锁 |
| **channel 缓冲** | 缓冲区大小合理，防阻塞/溢出 |

### 缓存策略

| 检查项 | 说明 |
|--------|------|
| **缓存穿透** | 热点数据缺缓存导致穿透 DB |
| **缓存雪崩** | 随机过期时间防大量同时过期 |
| **缓存击穿** | 热点 key 过期用互斥锁保护 |
| **缓存粒度** | 防缓存过大（页面而非片段） |
| **多级缓存** | 本地内存 + Redis 是否必要 |
| **失效策略** | TTL 合理 + 写操作清除相关缓存 |
| **预热** | 启动时预热关键数据 |

### 算法与数据结构

| 检查项 | 说明 |
|--------|------|
| **循环嵌套** | 隐式 O(n²)（循环内调 API/DB） |
| **集合查找** | list 频繁查找改 set/dict |
| **字符串拼接** | 循环中用 `StringBuilder` / `join` |
| **预分配** | 已知大小的 slice/list 预分配容量 |
| **延迟计算** | 大集合用 generator / pagination |
| **不必要排序** | 检查是否真的需要有序 |
| **批量操作** | 逐条改批量（batch insert/API） |

### 内存管理

| 检查项 | 说明 |
|--------|------|
| **大对象引用** | 防长期持有不再使用的大对象 |
| **循环引用** | 防 GC 无法回收（Python/JS） |
| **对象池** | 热路径频繁创建销毁的对象复用 |
| **闭包泄漏** | 回调意外捕获大对象 |
| **文件描述符** | 文件/连接正确关闭 |
| **缓冲区复用** | byte buffer 复用防频繁分配 |

### 网络与 I/O

| 检查项 | 说明 |
|--------|------|
| **Keep-Alive** | HTTP 连接复用 |
| **超时设置** | connect/read/write 超时合理 |
| **重试策略** | exponential backoff + jitter 防雪崩 |
| **压缩** | 大响应体 gzip/brotli |
| **数据量裁剪** | API 防过度 fetch |
| **批处理** | 小请求合并批量 |
| **预读取** | 已知数据提前异步加载 |

---

## 前端性能

### 渲染性能

| 检查项 | 说明 |
|--------|------|
| **不必要重渲染** | 缺 memo 导致频繁重渲染 |
| **key 属性** | 不用 index 防全量 Diff |
| **大列表** | 用虚拟滚动（react-window） |
| **瀑布流请求** | 防串行依赖请求 |
| **状态提升** | 状态放太低导致大范围重渲染 |
| **计算属性** | 复杂计算用 `useMemo`/`computed` |
| **动画性能** | 用 `transform`+`opacity`（GPU） |

### 包体积与加载

| 检查项 | 说明 |
|--------|------|
| **代码分割** | 大页面用 `import()` / `lazy()` 按需加载 |
| **Tree Shaking** | 防未使用的导入 |
| **图片优化** | WebP/AVIF + 懒加载 |
| **字体优化** | `font-display: swap` + 子集化 |
| **第三方库** | 防大库只用小部分功能 |
| **CSS 优化** | 去无用 CSS，提取重复样式 |

### 用户交互

| 检查项 | 说明 |
|--------|------|
| **防抖/节流** | 高频事件（搜索/滚动/resize） |
| **骨架屏** | loading 态防布局抖动 |
| **预加载** | hover 时 `<link rel="prefetch">` |
| **即时反馈** | 乐观更新，不等 API |
| **长任务** | Web Worker / setTimeout 分片 |

### 网络请求

| 检查项 | 说明 |
|--------|------|
| **请求合并** | 短时间多个 API 请求合并 |
| **数据预取** | 关键数据 HTML 内联 |
| **缓存策略** | 静态资源 `Cache-Control` / `ETag` |
| **CDN 使用** | 静态资源是否通过 CDN 分发 |
| **HTTP/2** | 是否开启了 HTTP/2 的多路复用而非雪崩式连接 |
| **Service Worker** | 离线可用场景是否使用了 Service Worker 缓存 |

## Profile 工具速查

| 场景 | 工具 |
|------|------|
| Python CPU/内存 | `cProfile` / `py-spy` / `memory_profiler` |
| Python async | `asyncio` debug mode / `aiomonitor` |
| TypeScript/Node | Chrome DevTools Profiler / `clinic` |
| React | React DevTools Profiler / `why-did-you-render` |
| 前端 Bundle | `webpack-bundle-analyzer` / `vite inspect` |
| Go | `pprof` / `trace` / `benchstat` |
| Rust | `perf` / `flamegraph` / `criterion` |
| Dart/Flutter | DevTools Profiler |

## 优化优先级

```
1️⃣ Profile → 定位瓶颈
2️⃣ 网络/IO → 连接池、缓存、批处理、压缩
3️⃣ 并发 → 独立任务并行化、避免阻塞
4️⃣ 算法 → O(n²) → O(n log n)、集合查找优化
5️⃣ 内存 → 泄漏修复、大对象释放、对象池
6️⃣ 渲染（前端）→ 不必要的重渲染、虚拟列表、代码分割
7️⃣ 验证 → 优化后再次 profile 确认提升
```
