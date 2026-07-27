---
applyTo: '**/*.{dart}'
---

# Dart / Flutter Debug Rules

> **AI Summary**: Dart 调试：dart analyze→DevTools→热重载→Null Safety/Widget/异步排查。

策略：**静态分析 + DevTools + 热重载**。

## 调试脚本

```powershell
# ── 静态分析 ──
dart analyze                                   # 全部
dart analyze lib/suspected_file.dart           # 指定文件
dart analyze --fatal-infos > analysis-errors.log  # 输出到文件

# ── 测试 ──
dart test                                      # 全部
dart test test/specific_test.dart              # 指定文件
dart test --reporter expanded                  # 详细输出
dart test --no-cache                           # 不缓存

# ── Flutter ──
flutter run --debug                            # Debug 模式
flutter run --profile                          # Profile 模式
flutter build web --debug                      # Web 调试构建

# ── DevTools ──
flutter pub global activate devtools && dart devtools  # 启动
# 或 IDE: Dart: Open DevTools

# ── 代码生成 ──
dart run build_runner clean && dart run build_runner build --delete-conflicting-outputs  # 清理重生成
dart run build_runner watch --delete-conflicting-outputs  # Watch 模式
```

## 常见问题与排查

### 编译错误

| 错误类型 | 排查方向 |
|---------|---------|
| **Compile-time error** | 检查类型注解、`?` 和 `!` 的使用 |
| **Analysis error** | 运行 `dart analyze` |
| **Asset not found** | 检查 pubspec.yaml → `flutter:` → `assets:` |
| **Missing entry point** | 检查 `lib/main.dart` |

### Null Safety

```dart
// 排查: ?. (安全访问) → ?? (默认值) → late → required
// DEBUG: [function] value=%s, isNull=%b
```

### Widget 不更新

```dart
ListView.builder(
  itemBuilder: (context, index) => ListTile(key: ValueKey(item.id)),
);  // 列表项必须有唯一 key
// DEBUG: [Widget] setState called | reason=%s
// 用 context.watch() 监听变化，const 构造函数避免不必要重建
```

### 异步问题

```dart
// 检查: await 遗漏 / StreamSubscription 未 cancel / Isolate SendPort 配对
// DEBUG: [function] async start/complete | args=%o, result=%o
```

### 布局溢出

```dart
// DevTools Layout Explorer 分析
// Container(color: Colors.red.withOpacity(0.3))  // 临时标记 widget 区域
```

### 网络请求

```dart
import 'dart:developer' as developer;
developer.log('Request sent', name: 'api', value: {'url': url});  // DevTools 查看

// 使用 http 拦截器
// 在 Dio 或 http 客户端中添加 LogInterceptor
// Dio().interceptors.add(LogInterceptor(requestBody: true, responseBody: true));
```

## 打点规范

```dart
// 使用 dart:developer 的 log（兼容 DevTools）
import 'dart:developer' as developer;

// 打点
developer.log('enter', name: 'MyClass.method', value: {'arg': arg});
developer.log('exit', name: 'MyClass.method', value: {'result': result});

// 临时 stdout 打点（用于终端调试）
// DEBUG: [MyClass.method] enter | arg=$arg
// DEBUG: [MyClass.method] exit | result=$result
```

## Flutter 特有调试技巧

```dart
// 1. 启用 Debug Paint 查看布局边界
// 在 main() 中添加：
// import 'package:flutter/rendering.dart';
// RendererBinding.instance.setDebugPaintEnabled(true);

// 2. 启用 Performance Overlay
// MaterialApp(showPerformanceOverlay: true);

// 3. 检查重建原因
// 在 build 方法中添加 print 标记

// 4. 慢速动画调试
// MaterialApp(debugShowCheckedModeBanner: false);
// 在 DevTools 中启用 Slow Animations
```

## 调试流程

```
① dart analyze → 修复静态分析问题
② dart test → 确认测试通过
③ flutter run --debug → 运行时验证
④ 使用 DevTools（Timeline / Inspector / Memory）→ 深入分析
⑤ 最小复现 Widget → 隔离布局/状态问题
⑥ 修复后重新运行 dart analyze + dart test 回归验证
```
