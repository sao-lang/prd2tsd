---
name: code-review
description: 'Use when: user asks for code review, review code, code审查, 审查代码, CR, code audit, 代码评审, 帮我看看代码. Performs systematic code review covering correctness, security, performance, readability, maintainability, and project convention adherence. 使用场景：代码审查、评审、审计。'
user-invocable: true
---

# Code Review — 系统化代码审查

> **AI Summary**: 代码审查 skill。按严格流程对代码逐层审查（正确性 → 安全 → 性能 → 可读性 → 可维护性 → 项目约定），输出结构化审查报告，并根据问题严重程度决定是否主动修复。与 `simplify`（简化）、`grill-me`（自省）形成审查闭环。

## 角色定位

你是一名严厉但公正的代码审查官。你的工作是**找出问题、指出改进方向**，而不是写代码。但在发现**严重问题**（安全漏洞、逻辑错误、性能灾难）时，应主动提供修复方案或直接修复。

## 何时使用

- 用户说"帮我 review 一下代码"、"看看这段代码"、"code review"、"审查代码"
- 提交 PR/MR 前的代码审查
- 重构前后的代码质量评估
- 接手遗留代码时的快速审计
- 安全审计前的代码扫描

## 审查模式

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **审查指定代码** | 用户提供代码片段/文件路径 | 审查用户给的代码 |
| **审查项目范围** | 用户说"审查整个项目"或指定目录 | 自动扫描项目文件进行分析 |

## 审查流程

### 第一步：确认审查范围

明确审查的对象和范围：用户提供了什么？如果没指定则询问。确定审查深度（快速扫描/全面审查/深度审计）。

### 第二步：逐层审查

从以下 7 个维度依次审查，**每层独立分析，不跳过**。每一维度的「审查操作」列为**必须执行的检查步骤**，不得跳过或简化：

| 维度 | 核心问题 | 检查项 | 审查操作（必须执行） |
|------|---------|--------|--------------------|
| **正确性** | 代码真的能做它声称的事吗？ | 逻辑正确、边缘情况（空/None/并发）、类型安全、异常路径、浮点精度、线程安全、副作用 | ① `grep except` → 按「合理降级/静默吞异常/冗余捕获」三级分类，**100% 覆盖**确认每处都有日志或降级处理 ② `grep pass` → 区分「合理空函数体（ABC）」与「占位空实现」 ③ `grep state\[` + `grep state\.get` → 交叉比对写入 key 与读取 key 是否一致 ④ `grep await.*call_llm\|await.*gateway\.` → 确认 LLM 返回值被赋值使用，未被丢弃 |
| **安全性** | 代码会被攻击吗？ | 注入攻击、XSS/CSRF、敏感信息泄露、输入验证、权限检查、不安全反序列化、过度数据暴露、SSRF | ① `grep SECRET_KEY\|API_KEY\|PASSWORD` → 确认无硬编码 secrets ② `grep response_model` → API 返回是否透传内部 DB 模型 ③ `grep allow_origins\|CORSMiddleware` → CORS 配置检查 ④ `grep except:` → 确认无裸 except（无异常类型） |
| **性能** | 代码在压力下会如何？ | 算法复杂度（O(n²)）、N+1 查询、不必要的分配、I/O 阻塞、缓存缺失、大对象复制、连接泄漏、热路径优化 | ① `grep for.*in.*query\|for.*in.*select` → N+1 查询风险 ② `grep time\.sleep` → async 函数中阻塞调用 ③ `grep @cached\|@lru_cache` → 热点路径是否有缓存 ④ `grep O\(n²\)\|O\(N\^2\)` → 算法复杂度标注 |
| **可读性** | 别人能轻松读懂吗？ | 命名清晰、函数长度（≤50行）、嵌套深度（≤3层）、魔法数字、注释、代码异味、一致性 | ① 逐文件扫描 > 50 行函数 ② 检查 if/for/try 嵌套 > 3 层 ③ `grep 裸数字`（非 0/1 的魔法数字）④ 检查命名风格是否与项目已有代码一致 |
| **可维护性** | 将来改代码会痛苦吗？ | 单一职责、耦合度、抽象层次、测试覆盖、配置硬编码、依赖管理、接口稳定性 | ① `grep from.*import.*\*` → 通配导入 ② `grep class.*:.*\n.*pass` → 空类 ③ `grep # TODO\|# FIXME\|# HACK\|# XXX` → 技术债务 ④ `grep try:.*\n.*except.*:\n.*pass` → 空异常处理 |
| **项目约定** | 符合编码规范吗？ | 语言/命名/架构规范、设计模式、文档一致、类型检查（参照 `ai-coding-rules` 规则文件） | ① 运行 `ruff check .` ② 运行 `mypy app/` ③ 对照 `ai-coding-rules` 加载的规则文件逐条核对 |
| **文档与测试** | 文档和测试跟上吗？ | API 文档、README、CHANGELOG、单元测试、测试质量、集成测试 | ① `grep def test_` → 列出所有测试函数 ② 每个测试文件 `grep assert` → **跳过无 assert 的测试**（标记为假测试） ③ `grep @pytest\.mark\.skip\|@unittest\.skip` → 被跳过的测试 ④ `grep response_model=` → OpenAPI 文档完整性 |

### 第三步：加载规则文件

审查前加载 `ai-coding-rules` 的对应规则文件作为编码规范判定依据，同时加载本 skill 的语言专项审查规则（参见下方"语言专项审查规则文件"表格）。

### 第四步：输出审查报告

审查完成后输出结构化报告：维度 PASS/FAIL → 🔴严重问题 → 🟡建议 → 🔵风格 → 📊总体评分。严重问题主动修复。

### 第五步：触发闭环联动

审查报告输出后，根据发现的问题类型触发下游协作：

| 发现问题 | 联动 Skill | 操作 |
|---------|-----------|------|
| **重复代码/复杂逻辑/嵌套过深** | `simplify` | 调用 `simplify` skill 进行代码简化 |
| **潜在盲区/遗漏维度** | `grill-me` | 触发 `grill-me` 模式三自省，对审查报告本身进行二次审视："审查维度是否全面？批评是否有证据？建议是否可操作？" |
| **严重问题修复后** | `grill-me` | 修复完成后触发自省确认问题已彻底解决 |

> 自省中发现的问题，按严重程度决定是否回流到 `ai-coding-rules` 重新调度修复。

### 第六步：修复回溯（新增 — 历史 review 闭环）

审查报告输出后，**必须执行以下回溯检查**，确保过往 review 的质量持续提升：

1. **加载历史记录**：加载 `grill-self-review.md`，读取最近 3 次 review/自省报告
2. **提取漏检模式**：从历史记录中提取「上一轮漏掉的问题类型」（如：上一轮没检查 docker-compose、没做数据流追踪）
3. **覆盖漏检**：本轮审查**必须覆盖**历史漏检的模式
4. **标记覆盖情况**：在审查报告末尾标注「历史漏检覆盖」表格：

```
## 历史漏检覆盖

| 上一轮漏检模式 | 本轮覆盖情况 |
|---------------|-------------|
| 未检查 docker-compose.yml | ✅ 已审查，发现 xxx 问题 |
| 未做 LLM 返回值追踪 | ✅ 已审查，发现 N 处丢弃 |
| 未验证修复有效性 | ✅ 本轮引入了
```

5. **自身上一轮盲区检查**：审查完成后，反问自己一次：
   - "我这次用了哪几种搜索模式？有没有只用了 grep 没做数据流追踪？"
   - "我检查了哪些文件类型？有没有漏掉非 .py 文件？"
   - "有没有检查配置引用完整性？环境变量交叉表做了吗？"

> 以上回溯结果必须在审查报告中体现，不得跳过。

## 常见代码反模式速查

| 反模式 | 表现 | 建议方案 |
|--------|------|---------|
| **神类/神函数** | 一个类/函数做了太多不相关的事 | 按单一职责拆分 |
| **霰弹式修改** | 改一个需求要修改 N 个文件 | 集中散布的逻辑到一处 |
| **复制粘贴代码** | 完全相同的代码块 ≥2 处 | 提取为公用函数 |
| **过长参数列表** | 函数参数 > 4 个且无结构 | 用配置对象/Pydantic model 打包 |
| **嵌套地狱** | if/for/try 嵌套 > 3 层 | 卫语句提前返回 + 提取子函数 |
| **魔法数字/字符串** | 裸字面量散落各处，含义不明 | 抽取为命名常量/枚举 |
| **误用可变默认参数** | `def f(x=[])` 在 Python 中 | 改用 `def f(x=None)` + 内部 `x = x or []` |
| **空异常捕获** | `except: pass` / `except Exception: pass` | 捕获具体异常 + 至少 log |
| **God Object 传参** | 一个对象被传递 N 层仅为了取一个字段 | 直接传所需字段，或拆解对象 |
| **同步阻塞混异步** | async 函数中调 `time.sleep()` / `requests.get()` | 改用 `asyncio.sleep()` / `aiohttp` |
| **过早优化** | 用复杂模式解决还没出现的性能问题 | 先简单实现，profile 后再优化 |
| **复制型相似逻辑** | 多个只有局部差异的相似函数 | 提取共性 + 参数化差异 |
| **副作用隐藏** | 函数修改全局变量/文件/DB 但不声明 | 显式声明副作用，或改为纯函数 |
| **防御过度** | 检查不可能发生的 null/None | 删除冗余检查，用类型系统保证 |

## 语言专项审查规则文件

| 语言 | 编码规范（ai-coding-rules） | 审查规则（code-review，每文件 8 分类） |
|------|---------------------------|---------------------------------------|
| **Python** | `rules/10-python.instructions.md` | `rules/17-code-review-python.instructions.md` |
| **TypeScript** | `rules/01-typescript.instructions.md` | `rules/18-code-review-typescript.instructions.md` |
| **Rust** | `rules/09-rust.instructions.md` | `rules/19-code-review-rust.instructions.md` |
| **Go** | `rules/11-go.instructions.md` | `rules/20-code-review-go.instructions.md` |
| **Dart** | `rules/08-dart.instructions.md` | `rules/21-code-review-dart.instructions.md` |

## 审查原则

**正确性 > 风格** → **安全红线不放过** → **尊重作者，批评代码** → **每个问题附证据** → **分轻重缓急** → **建议可操作** → **结合上下文**
