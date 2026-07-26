---
applyTo: '**/*.{ts,tsx}'
---

# TypeScript / TSX Debug Rules

> **AI Summary**: TypeScript 调试。类型检查→测试→DevTools→最小复现。

策略：**类型系统优先，运行时验证兜底**。

## 调试脚本

### 类型检查

```powershell
pnpm exec tsc --noEmit --pretty           # 严格模式（首步必做）
pnpm exec tsc --noEmit --pretty --project packages/components/tsconfig.json  # 指定包
pnpm exec tsc --noEmit --pretty | Select-String "src/file.ts"                # 指定文件
pnpm exec tsc --noEmit --pretty 2>&1 | Out-File tsc-errors.log               # 输出报告
pnpm exec tsc --noEmit --pretty --watch   # Watch 增量
pnpm exec tsc --traceResolution --noEmit 2>&1 | Select-String "module"       # 模块解析追踪
```

### Source Map 调试

```powershell
# tsconfig 需 "sourceMap": true，DevTools/IDE 设断点单步执行源码
```

### 依赖类型声明

```powershell
pnpm ls --depth=0 -r | Select-String "@types"         # 查找 @types 包
Get-Content "node_modules/@types/react/index.d.ts" -Head 50  # 查看类型定义
Get-Content tsconfig.json | ConvertFrom-Json | Select-Object -ExpandProperty compilerOptions | Select-Object paths, baseUrl  # paths 配置
node -e "console.log(require.resolve('some-module'))"  # 模块实际路径
```

### Lint 检查

```powershell
pnpm exec eslint 'packages/**/*.{ts,tsx}' --max-warnings 0 --format stylish  # 检查
pnpm exec eslint 'packages/**/*.{ts,tsx}' --fix       # 自动修复
pnpm exec eslint 'packages/**/*.{ts,tsx}' --format json --output-file lint-output.json  # JSON 输出
```

### 单元测试

```powershell
pnpm exec vitest run                                    # 全部
pnpm exec vitest run test/components/ActionButton.test.tsx  # 指定文件
pnpm exec vitest run --coverage                         # 覆盖率
pnpm exec vitest run --reporter verbose --passWithNoTests   # 仅失败
pnpm exec vitest --ui                                   # UI 模式
```

### 构建调试

```powershell
pnpm run build                                         # 全部
pnpm --filter @lania-pro-components/components run build  # 指定包
pnpm run clean && pnpm run build                       # 清理后重构建
pnpm exec rollup -c rollup.config.js --bundleConfigAsCjs  # rollup 详情
```

### 日志分析

```powershell
Select-String -Path "packages/**/*.{ts,tsx}" -Pattern "// DEBUG:|console\.\w+\(" -CaseSensitive | Group-Object Filename  # 临时日志
Select-String -Path "packages/**/*.{ts,tsx}" -Pattern "TODO|FIXME|HACK|XXX" -CaseSensitive  # TODO/FIXME
Select-String -Path "packages/**/*.{ts,tsx}" -Pattern "^\s*//\s*(console|debugger|export|function|class)" -CaseSensitive  # 注释掉的代码
```

### 性能调试

```powershell
Get-ChildItem -Recurse -Include *.ts,*.tsx | Where-Object { $_.Length -gt 100KB } | Select-Object Name, Length | Sort-Object Length -Descending  # 大文件
Get-ChildItem -Recurse -Directory packages | ForEach-Object { $files = Get-ChildItem $_.FullName -Recurse -Include *.ts,*.tsx; [PSCustomObject]@{Package = $_.Name; Files = $files.Count} } | Sort-Object Files -Descending  # 各包文件数
```

### 文件变更追踪

```powershell
Get-ChildItem -Recurse -Include *.ts,*.tsx | Sort-Object LastWriteTime -Descending | Select-Object -First 20 Name, LastWriteTime  # 最近修改
git diff --name-only HEAD~1                           # Git 变更
git log --oneline --follow -- packages/components/src/ProTable/index.tsx  # 文件历史
```

### 一键诊断

```powershell
function Invoke-QuickDiagnose {
    Write-Host "=== Type Check ===" -ForegroundColor Cyan
    pnpm exec tsc --noEmit --pretty 2>&1 | Out-Host
    Write-Host "=== Lint ===" -ForegroundColor Cyan
    pnpm exec eslint 'packages/**/*.{ts,tsx}' --max-warnings 0 2>&1 | Out-Host
    Write-Host "=== Test (failed only) ===" -ForegroundColor Cyan
    pnpm exec vitest run --reporter verbose 2>&1 | Out-Host
}
```

### 打点调试

```powershell
Select-String -Path "packages/**/*.{ts,tsx,js,jsx}" -Pattern "// DEBUG:" -CaseSensitive  # 查找 DEBUG 标记
```

```typescript
// DEBUG: [Component.method] enter | input=%o
// DEBUG: [Component.method] type check | isArray=%o, typeof value=%s
// DEBUG: [Component.method] branch=if-case | condition=%o
// DEBUG: [Component.method] return | result=%o
// const start = performance.now();
// // ... code ...
// // DEBUG: [Component.method] took %d ms, performance.now() - start
```

### 最小复现

```typescript
// debug-isolate.test.ts — 最小复现测试
import { describe, it, expect } from 'vitest';
type Input = { /* ... */ };
const minimalInput: Input = {/* ... */};
const expectedOutput = {/* ... */};
describe('Bug: [问题简述]', () => {
  it('reproduces issue', () => {
    const result = someFunction(minimalInput);
    expect(result).toEqual(expectedOutput);
  });
  it('passes when [条件]', () => {
    const modifiedInput = { ...minimalInput };
    const result = someFunction(modifiedInput);
    expect(result).not.toEqual(expectedOutput);
  });
});
```

```powershell
# 对 TS 项目使用 vitest 作为 bisect 验证命令
git bisect start
git bisect bad
git bisect good <已知正常 commit>
git bisect run pnpm exec vitest run test/specific-test.tsx
git bisect reset
```

## 错误分类与排查策略

### 类型错误（编译期）

```powershell
# 定位错误位置
pnpm exec tsc --noEmit --pretty
```

- 检查类型定义是否匹配，泛型参数是否正确传递
- 检查第三方库类型声明（`@types/xxx`）是否存在或版本匹配

#### 类型推断不符合预期

```typescript
// 用 satisfies 验证类型但不改变推断结果
const result = someFunction(input) satisfies ExpectedType;

// 用临时类型变量暴露推断结果
const _debugType: ExpectedType = someFunction(input);
// ↑ 如果这行报错，说明推断类型与预期不匹配
```

#### 泛型约束错误

```typescript
// 明确标注泛型参数来缩小范围
function debugGeneric<T extends Constraint>(arg: T) {
  // 在调用处显式传入类型参数
}
// 调用：debugGeneric<ConcreteType>(arg);
```

#### 交叉类型/联合类型问题

```typescript
// 使用 Discriminated Union 区分分支
type Result = { status: 'success'; data: unknown } | { status: 'error'; message: string };

// 用类型谓词收窄类型
function isSuccess(r: Result): r is { status: 'success'; data: unknown } {
  return r.status === 'success';
}
```

#### Module Resolution 错误

```powershell
pnpm exec tsc --traceResolution --noEmit 2>&1 | Select-String "some-module"
```

- 检查 `tsconfig.json` 中 `paths` / `baseUrl` 配置
- 检查 `package.json` 中 `exports` / `types` 字段

#### 异步类型错误

```typescript
// 确保 Promise 类型链完整
async function debugAsync(): Promise<ResultType> {
  const data = await fetchData(); // 检查 fetchData 返回类型
  return processData(data); // 检查 processData 返回类型
}
// 用 ReturnType 检查函数返回类型
type FetchReturn = ReturnType<typeof fetchData>;
```

### 运行时错误

- 区分：TypeError（undefined 调用）、RangeError（递归溢出）、ReferenceError（未定义变量）
- 检查异步操作中 `await` 是否遗漏
- 检查可选链 `?.` 和空值合并 `??` 的使用是否合理

### 渲染问题（React）

- **不更新**：检查 props 引用是否变化（`React.memo` 依赖）、Context 值是否更新
- **无限重渲染**：检查 `useEffect` 依赖数组、`useCallback`/`useMemo` 依赖链
- **样式异常**：检查 CSS 类名冲突、CSS-in-JS 运行时值、样式优先级

#### React TSX 特有调试

```typescript
// 检查 props 类型是否匹配
type Props = {
  onSave: (data: Data) => void;
  items: Item[];
};

// 检查泛型组件类型
const GenericComponent = <T extends unknown>(props: Props<T>) => {
  const _check: Props<T> = props;
};
```

### 状态管理问题

- 追踪 store 变更时序
- 检查 watch/effect 依赖项
- 注意批量更新队列（React 18 auto-batching）

### 异步时序问题

- 检查竞态条件（请求覆盖、过期响应处理）
- 检查 cleanup 函数是否执行
- 检查 Promise 链是否有未 `await` 的调用

### 网络请求问题

- 检查请求/响应 payload 与预期是否一致
- 检查状态码和错误处理分支
- 检查 CORS 配置
- 检查请求时序（并发请求、取消请求）

### 构建/打包问题

- 检查 rollup/vite 配置
- 检查外部依赖声明（`external`/`peerDependencies`）
- 检查产物内容：`pnpm exec rollup -c rollup.config.js --bundleConfigAsCjs`

## 输出规范

除通用调试报告外，TS 调试需额外包含：

- `tsc --noEmit` 的错误行号和错误码
- 涉及的类型定义文件路径及行号
- `tsconfig.json` 中相关编译选项配置
