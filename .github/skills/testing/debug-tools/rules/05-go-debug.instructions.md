---
applyTo: '**/*.{go}'
---

# Go Debug Rules

> **AI Summary**: Go 调试：go vet→race 检测→delve→pprof→table-driven 测试。

策略：**静态检查 + 单元测试 + pprof + delve**。

## 调试脚本

```powershell
# ── 静态检查 ──
go build ./...                                   # 编译
go vet ./...                                     # Vet
go vet -v ./...                                  # Vet 详细

# ── 测试 ──
go test ./...                                    # 全部
go test ./internal/suspected/...                 # 指定包
go test -run TestFunctionName ./...              # 指定函数
go test -v -run TestFunctionName ./...           # 详细输出
go test -coverprofile=coverage.out ./... && go tool cover -html=coverage.out -o coverage.html  # 覆盖率

# ── Race 检测 ──
go test -race ./...                              # 测试时
go run -race main.go                             # 运行时

# ── Delve ──
go install github.com/go-delve/delve/cmd/dlv@latest  # 安装
dlv debug main.go                                # Debug 启动
dlv attach <PID>                                 # 附加进程
dlv debug --headless --listen=:2345 --api-version=2  # 远程

# ── 性能分析 ──
go test -cpuprofile=cpu.prof -bench=. ./...      # CPU
go test -memprofile=mem.prof -bench=. ./...      # 内存
go test -blockprofile=block.prof -bench=. ./...  # 锁竞争

# ── 格式化/Lint ──
gofmt -l -s ./                                   # 检查格式
gofmt -l -s -w ./                                # 自动修复
golangci-lint run ./...                          # golangci-lint
```

## 常见问题与排查

### 接口实现错误

```go
var _ SomeInterface = &MyStruct{}  // 编译报错 = 未实现
```

### nil 引用

```go
if obj != nil && obj.Field != nil { /* 安全访问 */ }
// DEBUG: [function] ptr=%v, isNil=%t
```

### 并发问题

```go
// go test -race ./... 检测数据竞争
select {
case result := <-ch:
case <-time.After(5 * time.Second):
    // DEBUG: [function] timeout
}
```

### 错误处理

```go
// go vet -vettool=$(go env GOPATH)/bin/errcheck 检查未处理错误
if err != nil {
    return fmt.Errorf("context: %w", err)  // 不要吞掉错误
}
```

### 内存泄漏

```powershell
go tool pprof -http=:8080 cpu.prof
go tool pprof -http=:8080 mem.prof
```
常见原因：Goroutine 未退出 / 全局 map 无限增长 / time.Ticker 未 Stop / defer 持大对象

### 类型断言

```go
if val, ok := someInterface.(ConcreteType); ok { /* 安全使用 */ }
```

### 测试调试

```go
// 表驱动测试 + 子测试（便于定位单个 case）
func TestSomething(t *testing.T) {
    tests := []struct {
        name string
        input Input
        want  Output
    }{
        {"case 1: normal", input1, output1},
        {"case 2: edge", input2, output2},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Something(tt.input)
            if !reflect.DeepEqual(got, tt.want) {
                // DEBUG: [TestSomething] mismatch | got=%v, want=%v
                t.Errorf("Something() = %v, want %v", got, tt.want)
            }
        })
    }
}
```

## 打点规范

```go
// 1. fmt.Printf 打点（快速验证）
// DEBUG: fmt.Printf("[function] entry: input=%+v\n", input)
// DEBUG: fmt.Printf("[function] exit: result=%+v\n", result)

// 2. log 包打点（带时间戳，适合长期观察）
// DEBUG: log.Printf("[function] state=%s, value=%d", state, value)

// 3. testing.T.Log 打点（测试用，仅 -v 时显示）
// t.Logf("DEBUG: [function] key=%s", key)
```

## 调试流程

```
① go vet ./... → 修复静态问题
② go build ./... → 确认编译通过
③ go test -race ./... → 修复并发和数据竞争问题
④ go run -race main.go → 运行时并发检测
⑤ 复杂逻辑用 dlv debug 单步执行
⑥ 性能问题用 pprof 分析 hot path
⑦ 修复后：go vet + go test -race + go build 回归验证
```
