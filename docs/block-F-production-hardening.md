# 块 F：生产级加固 — 工具系统 / 护栏 / 熔断 / 异步编排 / Provider Failover / 结构化输出 / 记忆增强 / Prompt 管理 / 行为回放

> **前置条件**：块 E 已完成且全部测试通过。本块在现有架构上做**增量增强**，不做架构重构。
> **核心目标**：将系统覆盖度从 ~55% 提升至 ~90%，补齐生产级 Agent 系统的全部关键缺口。

**新增功能（共 10 项）：**

---

## 1. 需求概览

| 优先级 | 功能 | 当前状态 | 目标状态 | 涉及模块 |
|--------|------|---------|---------|---------|
| 🔴 P0 | 工具系统（Tool Registry + Function Calling） | ❌ 不存在 | ✅ 4 个 Agent 共享工具注册器 | 新增 `app/agents/tools/` |
| 🔴 P0 | Provider Failover 链 | ⚠️ 硬编码 map | ✅ 自动化 Failover 链 | `app/llm_gateway/` |
| 🟡 P1 | Gateway 护栏拦截器 | ❌ 不存在 | ✅ 输入/输出可插拔护栏 | 新增 `app/llm_gateway/guardrails/` |
| 🟡 P1 | 统一 Task 抽象 | ⚠️ 无优先级/取消 | ✅ 优先级队列+取消+持久化 | `app/task_manager.py` + `app/batch/` |
| � P1 | 记忆层增强 | ⚠️ 占位实现 | ✅ 上下文压缩+记忆检索策略 | `app/session_history/` |
| 🟡 P1 | 多租户 Prompt 隔离 | ❌ 不存在 | ✅ 租户级自定义 Prompt | `app/auth/` |
| 🟢 P2 | Circuit Breaker | ❌ 不存在 | ✅ 装饰器式熔断器 | 新增 `app/core/circuit_breaker.py` |
| 🟢 P2 | 结构化输出 | ❌ 正则扒 JSON | ✅ response_format 原生约束 | `app/llm_gateway/providers/` |
| 🟢 P2 | Prompt 版本管理 | ❌ 不存在 | ✅ 版本化+回滚 | 新增 `app/core/prompt_registry.py` |
| 🟢 P2 | Agent 行为回放 | ❌ 不存在 | ✅ 决策日志+重演 | 新增 `app/observability/replay.py` |
| 🟡 P1 | 意图驱动的任务路由 | ❌ 不存在 | ✅ 自动分类+分流 | 新增 `app/orchestrator/intent_classifier.py` |

---

## 2. P0：工具系统（Tool Registry + Function Calling）

### 2.1 问题分析

当前 4 个 Agent Layer（Analysis/Planning/Generation/Evaluation）各自在 `tools.py` 中定义辅助函数：

```
analysis_layer/tools.py     → call_llm_async(), parse_markdown_sections(), extract_json_from_llm()
planning_layer/tools.py     → call_llm_async(), retrieve_knowledge()
generation_layer/tools.py   → call_llm_async()
evaluation/tools.py         → call_llm(), parse_score()
```

问题：
- ❌ LLM 不能自主选择工具（没有 Function Calling）
- ❌ 工具不能跨 Layer 复用（每个 Layer 自己写一份）
- ❌ 没有统一的 Tool Schema（无法给 LLM 描述工具能力）
- ❌ 没有工具鉴权、执行记录、超时控制

### 2.2 设计方案

#### 2.2.1 新增文件结构

```
app/agents/
├── __init__.py
├── registry.py          # ToolRegistry — 全局注册器
├── base.py              # BaseTool — 工具基类
├── context.py           # ToolContext — 工具执行的上下文
├── result.py            # ToolResult — 工具执行结果
└── tools/               # 具体工具实现
    ├── __init__.py
    ├── knowledge.py     # SearchKnowledgeTool, GetEntityTool
    ├── document.py      # ReadFileTool, SearchDocTool
    ├── llm.py           # CallLLMTool
    ├── code.py          # GenerateCodeTool, ReadCodeTool
    └── system.py        # ReadTimeTool, ListFilesTool (辅助工具)
```

#### 2.2.2 核心接口

```python
# app/agents/base.py

from abc import ABC, abstractmethod
from pydantic import BaseModel

class BaseTool(ABC):
    """工具基类 — 所有工具继承此类。"""

    name: str                                    # 工具名（LLM 通过此名选择）
    description: str                             # 描述（LLM 理解用途）
    parameters: type[BaseModel]                  # Pydantic 参数模型 → 自动 JSON Schema
    required_permissions: list[str] = []         # 调用所需权限（可选）
    timeout: float = 30.0                        # 执行超时（秒）

    @abstractmethod
    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        """执行工具逻辑。子类必须实现。

        Args:
            ctx: 工具执行上下文（含 state/trace/workspace_id/llm 等）。
            **params: 由 LLM Function Calling 解析的参数。

        Returns:
            ToolResult 包含执行结果。
        """
        ...
```

```python
# app/agents/context.py

@dataclass
class ToolContext:
    """工具执行上下文 — 每个工具执行时注入。"""
    task_id: str
    workspace_id: str
    user_id: str
    trace_id: str
    state: dict                             # 当前 Agent State 的快照
    llm: LLMGateway                         # LLM 调用能力（工具也可调 LLM）
    db: AsyncSession | None = None          # 数据库会话
    services: dict[str, Any] = field(default_factory=dict)  # 其他服务
```

```python
# app/agents/result.py

@dataclass
class ToolResult:
    """工具执行结果。"""
    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # 执行统计
    duration_ms: float = 0.0
    tokens_consumed: int = 0
```

#### 2.2.3 ToolRegistry 设计

```python
# app/agents/registry.py

class ToolRegistry:
    """全局工具注册器 — 所有 Agent 共享。

    职责：
    - 注册/注销工具
    - 生成 JSON Schema（给 LLM Function Calling）
    - 按权限/角色筛选工具
    - 执行工具（含超时/鉴权/追踪）
    """

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """注册工具。重复注册会覆盖。"""
        cls._tools[tool.name] = tool

    @classmethod
    def get_schemas(
        cls,
        agent_name: str = "",
        permissions: list[str] | None = None,
    ) -> list[dict]:
        """返回工具的 OpenAI Function Calling Schema。

        Args:
            agent_name: 按 Agent 筛选（为空返回全部）。
            permissions: 按权限筛选（为空不限制）。

        Returns:
            OpenAI tools 参数格式的列表。
        """
        tools = cls._tools.values()
        if agent_name:
            tools = [t for t in tools if agent_name in t.allowed_agents]
        if permissions:
            tools = [
                t for t in tools
                if not t.required_permissions
                or all(p in permissions for p in t.required_permissions)
            ]
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters.model_json_schema(),
                },
            }
            for t in tools
        ]

    @classmethod
    async def execute(
        cls,
        name: str,
        ctx: ToolContext,
        **params: Any,
    ) -> ToolResult:
        """执行工具（含超时/追踪/鉴权）。

        Args:
            name: 工具名。
            ctx: 执行上下文。
            **params: 执行参数。

        Returns:
            ToolResult。

        Raises:
            ToolNotFoundError: 工具未注册。
            ToolPermissionError: 无权限调用。
            ToolTimeoutError: 执行超时。
        """
        tool = cls._tools.get(name)
        if not tool:
            raise ToolNotFoundError(name)

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                tool.execute(ctx, **params),
                timeout=tool.timeout,
            )
            result.duration_ms = (time.monotonic() - start) * 1000
            return result
        except asyncio.TimeoutError:
            raise ToolTimeoutError(name, tool.timeout)
```

#### 2.2.4 与 Gateway 的集成（Function Calling）

```python
# 在 LLMGateway.complete() 中新增 tools 参数

class LLMGateway:
    async def complete(
        self,
        prompt: str,
        task_type: str = "default",
        tools: list[dict] | None = None,     # ← 新增：Function Calling Schema
        tool_choice: str | dict = "auto",     # ← 新增：工具选择策略
        ...
    ) -> LLMResponse:
        ...
        provider = self.provider_factory.create(...)
        response = await provider.complete(
            prompt=prompt,
            model=model_name,
            tools=tools,                      # ← 传入 tools
            tool_choice=tool_choice,           # ← 传入 tool_choice
            ...
        )
        return response
```

```python
# OpenAIProvider 中透传 tools 参数

class OpenAIProvider(BaseProvider):
    async def complete(self, prompt, model="", **kwargs):
        tools = kwargs.pop("tools", None)
        tool_choice = kwargs.pop("tool_choice", None)
        params = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = tools
        if tool_choice:
            params["tool_choice"] = tool_choice
        response = await self._client.chat.completions.create(**params)
        ...
```

#### 2.2.5 在 Agent Node 中使用

```python
# 改造前：分析层 tools.py 的 call_llm_async（无工具）
async def call_llm_async(prompt, model=None):
    resp = await gateway.complete(prompt=prompt, task_type="analysis_requirement")
    return resp.content

# 改造后：Node 内让 LLM 自主选择工具
class RequirementExtractorNode:
    async def run(self, state: AnalysisState) -> AnalysisState:
        # 1. 获取当前 Agent 可用工具
        schemas = ToolRegistry.get_schemas(
            agent_name="analysis",
            permissions=state.get("permissions"),
        )
        # 2. 调用 LLM（允许选工具）
        resp = await gateway.complete(
            prompt=self._build_prompt(state),
            task_type="analysis_requirement",
            tools=schemas,
            tool_choice="auto",
        )
        # 3. 处理 tool_calls
        if resp.tool_calls:
            for tc in resp.tool_calls:
                ctx = ToolContext(
                    task_id=state["task_id"],
                    workspace_id=state["workspace_id"],
                    ...
                )
                result = await ToolRegistry.execute(
                    tc.function.name,
                    ctx=ctx,
                    **json.loads(tc.function.arguments),
                )
                state.tool_results.append(result)
        return state
```

### 2.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 能注册/注销工具 | `ToolRegistry.register(MyTool())` → `ToolRegistry._tools` 包含该工具 |
| 能按 Agent 筛选工具 Schema | `get_schemas(agent_name="analysis")` 只返回 analysis 层可用工具 |
| LLM 能选择并调用工具 | Mock LLM 返回 tool_call → `ToolRegistry.execute` 正确执行 |
| 工具执行超时控制 | 超时工具 → 抛 `ToolTimeoutError` |
| 工具执行鉴权 | 无权限用户调工具 → 抛 `ToolPermissionError` |
| 工具执行追踪 | 每次执行记录 duration_ms / tokens_consumed 到 Span |
| 4 个 Agent 共享工具 | `analysis` / `planning` / `generation` 均能调 `search_knowledge` |

---

## 3. P0：Provider Failover 链

### 3.1 问题分析

当前 Failover 逻辑：

```python
# llm_gateway/__init__.py — 预算降级
_provider_map = {"gpt-4o-mini": "openai", "deepseek-chat": "deepseek"}
downgrade_provider = _provider_map.get(low_cost_model, "openai")
```

问题：
- ❌ Failover 链是硬编码的，不是配置驱动的
- ❌ 没有 Provider 健康检测（不知道哪个 Provider 当前可用）
- ❌ 只有预算触发的降级，没有**调用失败**触发的切换
- ❌ Anthropic/Cohere Provider 都是桩代码，切换了也没用

### 3.2 设计方案

#### 3.2.1 配置驱动的 Failover 链

```yaml
# 在 config.py 或 .env 中定义
FAILOVER_CHAIN__LLM__PRIMARY: "deepseek:deepseek-chat"
FAILOVER_CHAIN__LLM__FALLBACKS: "openai:gpt-4o-mini,anthropic:claude-3-haiku"
FAILOVER_CHAIN__LLM__ULTIMATE: "local:llama-3"       # 终极兜底

FAILOVER_CHAIN__EMBEDDING__PRIMARY: "openai:text-embedding-3-small"
FAILOVER_CHAIN__EMBEDDING__FALLBACKS: "local:BAAI/bge-large-zh-v1.5"
```

#### 3.2.2 FailoverManager

```python
# 新增：app/llm_gateway/failover.py

@dataclass
class FailoverTarget:
    """Failover 目标。"""
    provider: str
    model: str
    priority: int         # 0=primary, 1=fallback, 2=ultimate
    healthy: bool = True
    last_check: float = 0.0

class FailoverManager:
    """Failover 管理器 — 自动切换 Provider。

    职责：
    - 维护每个 model_type 的 Failover 链
    - 定期健康检测（ping 每个 Provider）
    - 调用失败时自动切到下一个
    - 恢复后自动切回 Primary
    """

    def __init__(self):
        # {model_type: [FailoverTarget, ...]}
        self._chains: dict[str, list[FailoverTarget]] = {}
        # {model_type: 当前使用的索引}
        self._current_index: dict[str, int] = {}
        self._health_check_interval = 60.0  # 每 60 秒检测一次

    def configure(self, model_type: str, chain: list[FailoverTarget]) -> None:
        """配置 Failover 链。"""
        self._chains[model_type] = chain
        self._current_index[model_type] = 0

    async def get_target(self, model_type: str) -> FailoverTarget:
        """获取当前可用的目标。自动跳过不健康的。"""
        chain = self._chains.get(model_type, [])
        idx = self._current_index.get(model_type, 0)

        for offset, target in enumerate(chain[idx:], start=idx):
            if await self._is_healthy(target):
                self._current_index[model_type] = offset
                return target

        raise AllProvidersUnavailableError(model_type)

    async def record_failure(self, model_type: str, provider: str) -> None:
        """记录调用失败，自动切到下一个。"""
        chain = self._chains.get(model_type, [])
        for target in chain:
            if target.provider == provider:
                target.healthy = False
                break
        # 自动跳到下一个健康的目标
        self._current_index[model_type] = 0  # 重置从头找

    async def _is_healthy(self, target: FailoverTarget) -> bool:
        """检查目标是否健康（带缓存）。"""
        if not target.healthy:
            # 已经标记为不健康，等下次 health_check 恢复
            return False
        # 定期 ping 检测
        now = time.monotonic()
        if now - target.last_check > self._health_check_interval:
            target.healthy = await self._ping(target)
            target.last_check = now
        return target.healthy

    async def _ping(self, target: FailoverTarget) -> bool:
        """检测 Provider 是否可用（发一个最小请求）。"""
        try:
            config = config_manager.get_config("llm", target.provider)
            provider = ProviderFactory().create(config.provider, config)
            await provider.complete(
                prompt="ping",
                model=target.model,
                max_tokens=1,
            )
            return True
        except Exception:
            return False
```

#### 3.2.3 集成到 Gateway

```python
class LLMGateway:
    def __init__(self):
        self.failover = FailoverManager()
        self._init_failover_chains()

    def _init_failover_chains(self):
        """从配置初始化 Failover 链。"""
        # 从环境变量读取
        # FAILOVER_CHAIN__LLM__PRIMARY: "deepseek:deepseek-chat"
        # FAILOVER_CHAIN__LLM__FALLBACKS: "openai:gpt-4o-mini,anthropic:claude-3-haiku"
        for model_type in ["llm", "embedding", "rerank", "judge", "vision"]:
            chain = self._parse_chain_from_env(model_type)
            if chain:
                self.failover.configure(model_type, chain)

    async def complete(self, prompt, task_type, ...):
        model_config, model_name = self.config_manager.resolve_model(task_type)

        # 尝试 Failover 链
        last_error = None
        for attempt in range(3):  # 最多试 3 个 Provider
            try:
                target = await self.failover.get_target("llm")
                provider = self.provider_factory.create(target.provider, ...)
                response = await provider.complete(prompt, model=target.model, ...)
                return response
            except Exception as e:
                last_error = e
                await self.failover.record_failure("llm", target.provider)

        # 全部失败 → 返回降级响应
        logger.error("所有 LLM Provider 不可用: %s", last_error)
        return LLMResponse(content="[服务暂不可用，请稍后重试]")
```

### 3.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| Failover 链配置驱动 | 修改 `.env` 的 FAILOVER_CHAIN 后，切换生效 |
| Primary 失败自动切 Fallback | Mock primary 抛异常 → 自动调 fallback |
| Fallback 也失败切 Ultimate | 前两个都抛异常 → 自动调终极兜底 |
| Provider 健康检测 | `_ping()` 失败 → 标记 unhealthy → 跳过 |
| 恢复后自动切回 Primary | Primary 恢复健康 → 下一请求自动恢复 |

---

## 4. P1：Gateway 护栏拦截器

### 4.1 问题分析

当前系统有数据脱敏（DataMaskingEngine），但：
- ❌ 没有输入护栏（Prompt 注入、有害内容直接送给 LLM）
- ❌ 没有输出护栏（LLM 返回了敏感内容直接返回给用户）
- ❌ 护栏逻辑分散在各处，不可插拔

### 4.2 设计方案

#### 4.2.1 新增文件结构

```
app/llm_gateway/guardrails/
├── __init__.py
├── base.py                  # Guardrail 基类
├── manager.py               # GuardrailManager
├── prompt_injection.py      # Prompt 注入检测
├── content_safety.py        # 内容安全检测
├── pii_detector.py          # PII 检测
└── output_validator.py      # 输出格式校验
```

#### 4.2.2 核心接口

```python
# app/llm_gateway/guardrails/base.py

class GuardrailResult:
    """护栏检查结果。"""
    passed: bool
    blocked: bool = False
    reason: str = ""
    severity: str = "info"       # info / warning / critical
    masked_text: str | None = None  # 脱敏后的文本

class Guardrail(ABC):
    """护栏基类 — 可插拔。"""

    name: str                                      # 护栏名称
    stage: Literal["pre_llm", "post_llm"]           # 前置/后置

    @abstractmethod
    async def check(self, text: str, context: dict) -> GuardrailResult:
        """执行护栏检查。

        Args:
            text: 输入或输出文本。
            context: 上下文（含 task_type/user_id/workspace_id 等）。

        Returns:
            检查结果。
        """
        ...
```

#### 4.2.3 具体护栏实现

```python
# app/llm_gateway/guardrails/prompt_injection.py

class PromptInjectionGuardrail(Guardrail):
    """Prompt 注入检测护栏 — 前置。"""

    name = "prompt_injection"
    stage = "pre_llm"

    # 已知的注入模式
    INJECTION_PATTERNS = [
        r"(?i)ignore all previous instructions",
        r"(?i)disregard your system prompt",
        r"(?i)you are now (free|released|unlocked)",
        r"(?i)you must act as",
        r"(?i)you are not (an AI|a language model)",
        r"(?i)system prompt:",
        r"(?i)forget everything",
        r"(?i)你被解放了",
        r"(?i)忽略之前的指令",
    ]

    async def check(self, text: str, context: dict) -> GuardrailResult:
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text):
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    reason=f"检测到 Prompt 注入模式: {pattern}",
                    severity="critical",
                )
        return GuardrailResult(passed=True)
```

```python
# app/llm_gateway/guardrails/content_safety.py

class ContentSafetyGuardrail(Guardrail):
    """内容安全检测护栏 — 后置。"""

    name = "content_safety"
    stage = "post_llm"

    # LLM 不应输出的内容类型
    BLOCKED_CONTENT = [
        r"(?i)(api_key|sk-[a-z0-9]{32,})",
        r"(?i)(secret|private_key)[\s:=]+['\"]?\w{16,}",
    ]

    async def check(self, text: str, context: dict) -> GuardrailResult:
        # 检测 LLM 是否泄露了敏感信息
        for pattern in self.BLOCKED_CONTENT:
            if re.search(pattern, text):
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    reason=f"输出包含敏感信息: {pattern}",
                    severity="critical",
                    masked_text=re.sub(pattern, "[MASKED]", text),
                )
        return GuardrailResult(passed=True)
```

#### 4.2.4 GuardrailManager

```python
# app/llm_gateway/guardrails/manager.py

class GuardrailManager:
    """护栏管理器 — 统一注册和执行所有护栏。"""

    def __init__(self):
        self._pre_guards: list[Guardrail] = []    # LLM 调用前
        self._post_guards: list[Guardrail] = []   # LLM 调用后

    def register(self, guard: Guardrail) -> None:
        """注册护栏。"""
        if guard.stage == "pre_llm":
            self._pre_guards.append(guard)
        else:
            self._post_guards.append(guard)

    async def check_input(self, text: str, context: dict) -> list[GuardrailResult]:
        """执行所有前置护栏。返回所有检查结果。"""
        results = []
        for guard in self._pre_guards:
            result = await guard.check(text, context)
            results.append(result)
            if result.blocked:
                logger.warning("输入被护栏拦截: %s — %s", guard.name, result.reason)
                break  # 一旦有人拦截就停止后续检查
        return results

    async def check_output(self, text: str, context: dict) -> list[GuardrailResult]:
        """执行所有后置护栏。返回所有检查结果。"""
        results = []
        for guard in self._post_guards:
            result = await guard.check(text, context)
            results.append(result)
            if result.blocked and result.severity == "critical":
                break
        return results
```

#### 4.2.5 集成到 Gateway

```python
class LLMGateway:
    def __init__(self):
        self.guardrails = GuardrailManager()
        self._init_guardrails()

    def _init_guardrails(self):
        """注册默认护栏。"""
        self.guardrails.register(PromptInjectionGuardrail())
        self.guardrails.register(PIIDetectorGuardrail())
        self.guardrails.register(ContentSafetyGuardrail())
        self.guardrails.register(OutputValidatorGuardrail())

    async def complete(self, prompt, task_type, ...):
        # ── 前置护栏 ──
        input_results = await self.guardrails.check_input(
            prompt, {"task_type": task_type, "workspace_id": workspace_id},
        )
        for r in input_results:
            if r.blocked:
                return LLMResponse(
                    content=f"[输入被护栏拦截: {r.reason}]",
                    metadata={"guardrail": r.name, "blocked": True},
                )

        # ── 调用 LLM ──
        response = await provider.complete(prompt, ...)

        # ── 后置护栏 ──
        output_results = await self.guardrails.check_output(
            response.content, {"task_type": task_type, "model": response.model},
        )
        for r in output_results:
            if r.blocked:
                if r.masked_text:
                    response.content = r.masked_text  # 自动脱敏
                else:
                    response.content = f"[输出被护栏拦截: {r.reason}]"
                    break

        return response
```

### 4.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| Prompt 注入被拦截 | 输入含 "忽略之前指令" → 返回 blocked 响应 |
| PII 泄露被拦截 | LLM 返回含 API Key → 自动脱敏或拦截 |
| 护栏可插拔 | `guardrails.register(MyGuardrail())` 后生效 |
| 护栏执行有记录 | 每次检查记录到 OpenTelemetry Span |
| 不阻断正常输入 | 正常 Prompt → 护栏全部 passed |

---

## 5. P1：统一 Task 抽象

### 5.1 问题分析

当前有两个独立的"任务管理"：

```python
# task_manager.py — 生成任务的 in-memory dict
class TaskManager:
    _tasks: dict[str, dict] = {}

# batch/tasks.py — 批量任务的 in-memory dict
class BatchTaskService:
    _tasks: dict[str, dict] = {}
```

问题：
- ❌ 两个独立实现，功能重复
- ❌ 无任务优先级（只能 FIFO）
- ❌ 无任务取消能力
- ❌ in-memory 存储，重启丢失
- ❌ 无任务队列（高并发时直接冲突）

### 5.2 设计方案

#### 5.2.1 统一 Task 模型

```python
# contracts/models.py — 新增

class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(StrEnum):
    GENERATE = "generate"           # PRD→TSD 生成
    REINDEX = "reindex"             # 文档重索引
    REGENERATE = "regenerate"       # 方案重新生成
    EVALUATE = "evaluate"           # 方案评测
    WEB_SYNC = "web_sync"           # Web 资源同步

class Task(BaseModel):
    """统一任务模型。"""
    id: str
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0                          # 0=最高, 越大越优先
    progress: float = 0.0
    total_steps: int = 1
    current_step: int = 0
    workspace_id: str = ""
    user_id: str = ""
    error_message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancellable: bool = True
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = Field(default_factory=dict)
```

#### 5.2.2 TaskQueue

```python
# app/core/task_queue.py — 新增

class TaskQueue:
    """统一任务队列 — 支持优先级 + 取消 + 持久化。

    使用 heapq 实现优先级队列，高优先级的任务先出队。
    支持 PostgreSQL 持久化（重启不丢失）。
    """

    def __init__(self, db_session_factory=None):
        self._mem_queue: list[tuple[int, float, Task]] = []  # (priority, time, task)
        self._running: dict[str, asyncio.Task] = {}           # 正在执行的任务
        self._session_factory = db_session_factory
        self._lock = asyncio.Lock()

    async def enqueue(self, task: Task) -> None:
        """入队。优先级越小越先执行。"""
        async with self._lock:
            heapq.heappush(self._mem_queue, (task.priority, time.monotonic(), task))
            await self._persist(task)  # 写数据库

    async def dequeue(self) -> Task | None:
        """出队 — 取优先级最高的任务。"""
        async with self._lock:
            if not self._mem_queue:
                return None
            _, _, task = heapq.heappop(self._mem_queue)
            return task

    async def cancel(self, task_id: str) -> bool:
        """取消任务。
        - 队列中未执行 → 从队列移除
        - 正在执行 → 取消 asyncio.Task
        """
        async with self._lock:
            # 检查是否在队列中
            for i, (_, _, t) in enumerate(self._mem_queue):
                if t.id == task_id:
                    self._mem_queue.pop(i)
                    heapq.heapify(self._mem_queue)
                    await self._update_status(task_id, TaskStatus.CANCELLED)
                    return True
            # 检查是否正在运行
            running_task = self._running.get(task_id)
            if running_task:
                running_task.cancel()
                self._running.pop(task_id)
                await self._update_status(task_id, TaskStatus.CANCELLED)
                return True
        return False

    async def get_status(self, task_id: str) -> Task | None:
        """查询任务状态。"""
        # 先查内存，再查数据库
        async with self._lock:
            for _, _, t in self._mem_queue:
                if t.id == task_id:
                    return t
            running_task = self._running.get(task_id)
            if running_task:
                return self._running_task_info.get(task_id)
        # 查数据库
        return await self._load_from_db(task_id)

    async def _persist(self, task: Task) -> None:
        """持久化到 PostgreSQL。"""
        if not self._session_factory:
            return
        # INSERT INTO tasks (...) VALUES (...) ON CONFLICT UPDATE

    async def worker(self) -> None:
        """工作循环 — 持续出队并执行任务。"""
        while True:
            task = await self.dequeue()
            if task is None:
                await asyncio.sleep(1)
                continue
            async with self._lock:
                self._running[task.id] = asyncio.create_task(
                    self._execute(task)
                )

    async def _execute(self, task: Task) -> None:
        """执行任务（含重试/超时/取消检测）。"""
        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(UTC)
            await self._persist(task)

            executor = TaskExecutorRegistry.get(task.type)
            await executor.run(task)

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(UTC)
            task.progress = 1.0
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
        except Exception as e:
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                await self.enqueue(task)  # 重新入队
            else:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
        finally:
            await self._persist(task)
            async with self._lock:
                self._running.pop(task.id, None)
```

#### 5.2.3 TaskExecutor 注册器

```python
# app/core/task_executor.py — 新增

class TaskExecutor(ABC):
    """任务执行器 — 每种 TaskType 一个实现。"""

    task_type: TaskType

    @abstractmethod
    async def run(self, task: Task) -> None:
        """执行任务逻辑。"""
        ...

class GenerateTaskExecutor(TaskExecutor):
    task_type = TaskType.GENERATE

    async def run(self, task: Task) -> None:
        orchestrator = build_orchestrator_graph(...)
        state = make_initial_state(task_id=task.id, ...)
        await orchestrator.ainvoke(state)

class ReindexTaskExecutor(TaskExecutor):
    task_type = TaskType.REINDEX

    async def run(self, task: Task) -> None:
        builder = KnowledgeGraphBuilder()
        for doc_id in task.metadata.get("document_ids", []):
            await builder.build_from_document(doc_id)
            task.current_step += 1
            task.progress = task.current_step / task.total_steps

class TaskExecutorRegistry:
    """任务执行器注册器。"""
    _executors: dict[TaskType, TaskExecutor] = {}

    @classmethod
    def register(cls, executor: TaskExecutor) -> None:
        cls._executors[executor.task_type] = executor

    @classmethod
    def get(cls, task_type: TaskType) -> TaskExecutor:
        exe = cls._executors.get(task_type)
        if not exe:
            raise ValueError(f"未注册的任务执行器: {task_type}")
        return exe
```

### 5.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 优先级队列 | 优先级 0 的任务比优先级 5 的先执行 |
| 任务取消 | `cancel(task_id)` → 正在执行的任务被取消 |
| 任务持久化 | 重启后未完成的任务仍在队列中 |
| 失败重试 | 执行异常 → 自动重试最多 3 次 |
| 进度上报 | `GET /tasks/{id}` 返回 progress / current_step |
| 统一管理 | generate + reindex + regenerate 共用同一队列 |

---

## 6. P2：Circuit Breaker 装饰器

### 6.1 设计方案

#### 6.1.1 核心熔断器

```python
# 新增：app/core/circuit_breaker.py

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class CircuitState(StrEnum):
    CLOSED = "closed"           # 正常工作
    OPEN = "open"               # 熔断
    HALF_OPEN = "half_open"     # 半开（试探恢复）


class CircuitBreakerError(Exception):
    """熔断器打开异常。"""

    def __init__(self, name: str, state: CircuitState) -> None:
        self.name = name
        self.state = state
        super().__init__(f"CircuitBreaker '{name}' 已打开")


class CircuitBreaker:
    """通用熔断器 — 可装饰任何异步函数。

    状态机：CLOSED → (连续失败 N 次) → OPEN → (等待超时) → HALF_OPEN
            → (试探成功) → CLOSED
            → (试探失败) → OPEN

    使用场景：LLM 调用、外部 API 调用、数据库查询等。
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ) -> None:
        """初始化熔断器。

        Args:
            name: 熔断器名称（用于日志和指标）。
            failure_threshold: 连续失败多少次后熔断。
            recovery_timeout: 熔断后等待多少秒进入半开状态。
            half_open_max_requests: 半开时允许的最大试探请求数。
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_requests = 0
        self._lock = asyncio.Lock()

    async def call(
        self,
        fn: Callable[P, Awaitable[R]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        """执行被熔断保护的异步函数。

        Args:
            fn: 异步函数。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            函数执行结果。

        Raises:
            CircuitBreakerError: 熔断器打开时抛出。
        """
        async with self._lock:
            # 检查当前状态
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_requests = 0
                    logger.info("熔断器 %s 进入半开状态", self.name)
                else:
                    raise CircuitBreakerError(self.name, self.state)

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_requests >= self.half_open_max_requests:
                    raise CircuitBreakerError(self.name, self.state)
                self.half_open_requests += 1

        # 执行函数
        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """成功回调 — 重置为 CLOSED。"""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_requests = 0
            logger.info("熔断器 %s 恢复为关闭状态", self.name)

    async def _on_failure(self) -> None:
        """失败回调 — 累计失败次数，阈值到达时熔断。"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    "熔断器 %s 已打开（连续失败 %d/%d）",
                    self.name, self.failure_count, self.failure_threshold,
                )

    @property
    def is_available(self) -> bool:
        """当前是否可用（用于查询）。"""
        return self.state != CircuitState.OPEN

    def reset(self) -> None:
        """手动重置熔断器。"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_requests = 0
        logger.info("熔断器 %s 已手动重置", self.name)

    def to_dict(self) -> dict[str, Any]:
        """导出状态（用于 Prometheus 指标和 API 查询）。"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "is_available": self.is_available,
        }
```

#### 6.1.2 装饰器模式

```python
# 装饰器 — 方便使用

def with_circuit_breaker(
    name: str | None = None,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """熔断器装饰器。

    Args:
        name: 熔断器名称（默认使用函数名）。
        failure_threshold: 熔断阈值。
        recovery_timeout: 恢复超时。

    Usage:
        @with_circuit_breaker(name="deepseek-api")
        async def call_deepseek(prompt: str) -> str:
            ...
    """
    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        cb = CircuitBreaker(
            name=name or fn.__name__,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return await cb.call(fn, *args, **kwargs)

        # 附加熔断器实例，方便外部查询状态
        wrapper.circuit_breaker = cb  # type: ignore[attr-defined]
        return wrapper

    return decorator


# CircuitBreakerManager — 统一管理所有熔断器

class CircuitBreakerManager:
    """熔断器管理器 — 统一注册/查询/监控。"""

    _breakers: dict[str, CircuitBreaker] = {}

    @classmethod
    def register(cls, breaker: CircuitBreaker) -> None:
        cls._breakers[breaker.name] = breaker

    @classmethod
    def get(cls, name: str) -> CircuitBreaker | None:
        return cls._breakers.get(name)

    @classmethod
    def get_all_status(cls) -> list[dict[str, Any]]:
        return [cb.to_dict() for cb in cls._breakers.values()]

    @classmethod
    def reset_all(cls) -> None:
        for cb in cls._breakers.values():
            cb.reset()
```

#### 6.1.3 在 Gateway 中使用

```python
# 在 LLMGateway 中，每个 Provider 配一个熔断器

class LLMGateway:
    def __init__(self):
        self._init_circuit_breakers()

    def _init_circuit_breakers(self):
        for provider_name in ["deepseek", "openai", "anthropic", "cohere"]:
            cb = CircuitBreaker(
                name=f"provider:{provider_name}",
                failure_threshold=3,       # LLM 调用连续 3 次失败就熔断
                recovery_timeout=30.0,     # 30 秒后试探恢复
            )
            CircuitBreakerManager.register(cb)

    async def complete(self, prompt, task_type, ...):
        model_config, model_name = self.config_manager.resolve_model(task_type)
        provider_name = model_config.provider

        # 熔断检查
        cb = CircuitBreakerManager.get(f"provider:{provider_name}")
        if cb and not cb.is_available:
            # 当前 Provider 熔断 → 走 Failover 链
            return await self._fallback_complete(prompt, task_type, exclude=[provider_name])

        try:
            provider = self.provider_factory.create(...)
            response = await cb.call(provider.complete, prompt, model_name)
            return response
        except CircuitBreakerError:
            # 熔断器已打开 → Failover
            return await self._fallback_complete(prompt, task_type, exclude=[provider_name])
```

### 6.2 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 连续失败 N 次后熔断 | Mock provider 抛 5 次异常 → 第 6 次直接抛 `CircuitBreakerError` |
| 熔断后自动恢复 | 等待 recovery_timeout → 半开状态 → 成功调用 → 恢复 CLOSED |
| 半开时限制请求数 | 半开时只允许 half_open_max_requests 个试探请求 |
| 装饰器可用 | `@with_circuit_breaker()` 装饰任意异步函数 |
| 熔断状态可查询 | `CircuitBreakerManager.get_all_status()` 返回所有状态 |
| Prometheus 指标 | 每次状态变化记录 counter/gauge |

---

## 7. P2：结构化输出

### 7.1 问题分析

当前所有 LLM 返回的 JSON 都是通过正则从文本中扒的：

```python
# analysis_layer/tools.py
def extract_json_from_llm(text: str) -> str:
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    brace_start = text.find("{")
    if brace_start >= 0:
        return text[brace_start:].strip()
```

问题：
- ❌ 解析不稳定（LLM 输出的格式稍微变化就解析失败）
- ❌ 浪费 token（LLM 输出多余的文本解释）
- ❌ 没有类型校验（解析失败只返回空值，没有报错）

### 7.2 设计方案

#### 7.2.1 OpenAI response_format 支持

```python
# contract/models.py — 新增

class StructuredOutputConfig(BaseModel):
    """结构化输出配置。"""
    enabled: bool = False
    schema: dict[str, Any] | None = None     # JSON Schema
    strict: bool = True                       # 严格模式
```

```python
# providers/openai.py — 新增 response_format 支持

class OpenAIProvider(BaseProvider):
    async def complete(self, prompt, model="", **kwargs):
        response_format = kwargs.pop("response_format", None)

        params = {
            "model": model_name,
            "messages": [...],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            params["response_format"] = response_format

        response = await self._client.chat.completions.create(**params)
        ...
```

#### 7.2.2 Pydantic 输出解析器

```python
# app/llm_gateway/output_parser.py — 新增

from pydantic import BaseModel, ValidationError


class PydanticOutputParser:
    """Pydantic 输出解析器 — 两步策略。

    策略：
    1. 优先使用 OpenAI response_format（原生 JSON 约束，最可靠）
    2. 降级使用 Prompt 约束 + 后处理解析
    """

    def __init__(self, pydantic_model: type[BaseModel]):
        self.pydantic_model = pydantic_model
        self.schema = pydantic_model.model_json_schema()

    def get_response_format(self) -> dict:
        """获取 OpenAI response_format 参数。"""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": self.pydantic_model.__name__,
                "strict": True,
                "schema": self.schema,
            },
        }

    def get_format_instruction(self) -> str:
        """获取 Prompt 格式指令（response_format 不可用时降级使用）。"""
        schema_str = json.dumps(self.schema, indent=2, ensure_ascii=False)
        return f"""
请严格按照以下 JSON Schema 输出，不要包含其他说明文字：
```json
{schema_str}
```
"""

    def parse(self, text: str) -> BaseModel:
        """解析 LLM 输出为 Pydantic 模型。

        步骤：
        1. 尝试直接 json.loads
        2. 尝试从 ```json 代码块提取
        3. 尝试从 { } 提取
        4. 全部失败 → 抛 ParseError
        """
        # 1. 尝试直接解析
        try:
            data = json.loads(text)
            return self.pydantic_model(**data)
        except (json.JSONDecodeError, ValidationError):
            pass

        # 2. 从 ```json 代码块提取
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return self.pydantic_model(**data)
            except (json.JSONDecodeError, ValidationError):
                pass

        # 3. 从第一个 { 提取
        brace_start = text.find("{")
        if brace_start >= 0:
            try:
                data = json.loads(text[brace_start:])
                return self.pydantic_model(**data)
            except (json.JSONDecodeError, ValidationError):
                pass

        raise OutputParseError(
            f"无法将 LLM 输出解析为 {self.pydantic_model.__name__}: {text[:100]}"
        )
```

#### 7.2.3 Prompt 生成器（带格式约束）

```python
# app/llm_gateway/prompt_builder.py — 新增

class PromptBuilder:
    """Prompt 构建器 — 统一管理 System Prompt + User Prompt + 格式约束。"""

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt

    def build(
        self,
        user_prompt: str,
        output_parser: PydanticOutputParser | None = None,
        use_response_format: bool = False,
    ) -> dict:
        """构建完整的 Prompt（含 system message）。

        Args:
            user_prompt: 用户输入。
            output_parser: 输出解析器（可选）。
            use_response_format: 是否使用 API 原生 JSON 模式。

        Returns:
            {"messages": [...], "response_format": ... | None}
        """
        messages = []

        # System prompt
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 格式指令（降级方案）
        if output_parser and not use_response_format:
            format_instruction = output_parser.get_format_instruction()
            if self.system_prompt:
                messages[0]["content"] += "\n\n" + format_instruction
            else:
                messages.append({"role": "system", "content": format_instruction})

        # User prompt
        messages.append({"role": "user", "content": user_prompt})

        result: dict = {"messages": messages}

        # response_format（原生方案）
        if output_parser and use_response_format:
            result["response_format"] = output_parser.get_response_format()

        return result
```

#### 7.2.4 在 Analysis Layer 中使用

```python
# 改造前：正则扒 JSON
async def call_llm_async(prompt, ...):
    resp = await gateway.complete(prompt=prompt, ...)
    return resp.content  # 文本 → 外面用 extract_json_from_llm

# 改造后：Pydantic 解析器 + response_format
from contracts.interfaces import RequirementDetail

parser = PydanticOutputParser(RequirementDetail)

# 两种策略：
# 策略 1：API 原生 response_format（推荐）
resp = await gateway.complete(
    prompt=prompt,
    response_format=parser.get_response_format(),  # ← OpenAI 原生 JSON 约束
    ...
)
requirement = parser.parse(resp.content)  # 100% 不会解析失败

# 策略 2：response_format 不可用时（如 DeepSeek 不支持）
prompt_with_format = prompt + "\n\n" + parser.get_format_instruction()
resp = await gateway.complete(prompt=prompt_with_format, ...)
requirement = parser.parse(resp.content)
```

### 7.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| response_format 生效 | LLM 返回直接是合法 JSON，无多余文本 |
| 降级解析可用 | response_format 不支持时，Prompt 约束 + 后处理也能工作 |
| 解析失败有明确报错 | LLM 返回格式错误 → 抛 `OutputParseError` |
| Pydantic 类型校验 | LLM 返回的字段类型不对 → ValidationError |
| 存量 Node 逐步迁移 | 迁移过程中新旧方案可共存 |

---

## 8. Claims 提取（知识层增强）

### 8.1 问题分析

当前知识层只提取实体（KGEntity），但 PRD 中大量有价值的**决策性断言**被丢弃：

```yaml
PRD 原文 → "系统必须使用 PostgreSQL 作为主数据库，QPS 不低于 5000"

当前提取结果:
  entity: "PostgreSQL" (type=TechStack)
  entity: "QPS" (type=Concept)           # 丢失了约束语义

期望提取的 Claim:
  type: constraint
  subject: "PostgreSQL"
  content: "必须使用 PostgreSQL 作为主数据库"

  type: specification
  subject: "系统"
  content: "QPS 不低于 5000"
```

问题：
- ❌ 实体提取只提取"名词"，丢失了"断言"（A 必须/不能/推荐 B）
- ❌ `models.py` 中 `Claim` 模型已定义但从未使用（死代码待清理，本块实现后恢复）
- ❌ TSD 生成时"约束条件"和"非功能性需求"章节缺乏直接证据来源

### 8.2 设计方案

#### 8.2.1 新增文件

```
app/knowledge_layer/ingestion/
├── ...
└── claims_extractor.py          # ← 新增：Claims 提取器
```

#### 8.2.2 ClaimsExtractor

```python
# app/knowledge_layer/ingestion/claims_extractor.py

"""Claims/Covariates 提取 — PRD 中的决策性断言提取。"""

from __future__ import annotations

from app.knowledge_layer.models import Chunk, Claim, ClaimType
from app.llm_gateway import gateway

CLAIMS_EXTRACTION_PROMPT = """你是一个技术文档断言提取专家。从以下文本中提取所有明确的决策性断言。

断言类型：
- decision: 明确的选型决策（如"使用 X 而不是 Y"）
- specification: 技术规格说明（如"支持 OAuth 2.0"）
- constraint: 约束条件（如"延迟 < 200ms"）
- comparison: 对比评估（如"X 比 Y 性能好 3 倍"）
- prediction: 预测性断言（如"预计 QPS 将达到 10000"）

请以 JSON 数组格式返回，每个断言包含：
{{
  "subject": "主体（技术实体或组件名）",
  "claim_type": "断言类型",
  "content": "断言的精确原文或摘要",
  "object": "客体（可选，如对比/约束的目标）"
}}

文本：
{text}

只返回 JSON 数组。"""


class ClaimsExtractor:
    """Claims 提取器 — 从文档分块中提取决策性断言。"""

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def extract(self, chunks: list[Chunk]) -> list[Claim]:
        """从分块中提取 Claims。

        Args:
            chunks: 文档分块列表。

        Returns:
            提取的 Claim 列表。
        """
        from app.core.logger import get_logger
        logger = get_logger("prd2tsd.knowledge.claims_extractor")

        all_claims: list[Claim] = []
        for chunk in chunks:
            claims = await self._extract_from_chunk(chunk)
            all_claims.extend(claims)

        logger.info("Claims 提取完成: %d claims", len(all_claims))
        return all_claims

    async def _extract_from_chunk(self, chunk: Chunk) -> list[Claim]:
        """从单个分块中提取 Claims。"""
        import json, uuid

        prompt = CLAIMS_EXTRACTION_PROMPT.format(text=chunk.text[:2000])
        try:
            resp = await gateway.complete(
                prompt=prompt,
                task_type="default",
                layer="knowledge",
                node="claims_extractor",
                model=self._model,
                temperature=0.1,
                max_tokens=2048,
            )
            data = self._parse_response(resp.content)
        except Exception:
            return []

        claims: list[Claim] = []
        for item in data:
            claim = Claim(
                id=str(uuid.uuid4()),
                subject=item.get("subject", ""),
                claim_type=item.get("claim_type", "specification"),
                content=item.get("content", ""),
                object=item.get("object", ""),
                source_text_unit_id=chunk.id,
            )
            if claim.subject and claim.content:
                claims.append(claim)
        return claims

    def _parse_response(self, response: str) -> list[dict]:
        """解析 LLM JSON 响应。"""
        import json, re
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
```

#### 8.2.3 存储方案

复用现有 PGVector 表结构，新增 `claim_embeddings` 表：

```python
# vector_store.py 新增建表

async def ensure_extensions(self) -> None:
    ...  # 现有逻辑
    await session.execute(
        text("""
            CREATE TABLE IF NOT EXISTS claim_embeddings (
                id VARCHAR(64) PRIMARY KEY,
                subject VARCHAR(256) NOT NULL,
                claim_type VARCHAR(32) NOT NULL,
                content TEXT NOT NULL,
                object TEXT DEFAULT '',
                embedding vector(1024),
                source_text_unit_id VARCHAR(64) DEFAULT '',
                workspace_id VARCHAR(64) DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
    )
```

#### 8.2.4 管线集成

```python
# pipeline.py KnowledgeGraphBuilder.build_from_document

# 在实体提取之后，添加上下文：
# 5b. Claims 提取
claims = await self.claims_extractor.extract(chunks)
for claim in claims:
    claim.workspace_id = workspace_id

# 5c. Claims Embedding + 存储
for claim in claims:
    claim_emb = await self.entity_embedder.embed_text(
        f"{claim.subject}: {claim.content}"
    )
    await self.vector_store.upsert_claim(claim, claim_emb)
```

#### 8.2.5 下游消费（TSD 生成）

```python
# 在 Generation Layer 中，检索时附带 Claims
class GenerateTSDNode:
    async def run(self, state):
        # 检索知识
        ctx = await pipeline.retrieve(query, mode="hybrid")

        # 检索 Claims（向量相似度）
        claim_results = await vector_store.search_claims(
            query=query, top_k=5
        )

        # Claims 直接注入 TSD 的"约束条件"和"非功能性需求"章节
        constraints = [c for c in claim_results if c.claim_type == "constraint"]
        specifications = [c for c in claim_results if c.claim_type == "specification"]
```

### 8.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| Claims 提取可用 | 输入含约束的 PRD 文本 → 返回 > 3 个 Claim |
| Claims 类型正确 | "必须"→ constraint, "推荐"→ decision, "支持"→ specification |
| Claims 持久化 | 提取后查 PGVector claim_embeddings 表有数据 |
| Claims 向量检索 | `search_claims("延迟要求")` 返回含"延迟 < 200ms"的 Claim |
| TSD 生成引用 Claims | TSD 的"约束条件"章节直接引用 Claim 原文 |

---

---

## 9. P1：记忆层增强（上下文压缩 + 记忆检索策略）

### 9.1 问题分析

当前记忆层：

```python
# session_history/summarizer.py — 占位实现
async def generate_title(self, first_message: str) -> str:
    return first_message[:50]  # 简单截取，没用 LLM

async def generate_summary(self, messages: list[dict]) -> str:
    return "; ".join(...)  # 拼接文本，没用 LLM
```

问题：
- ❌ **无上下文压缩**：对话越长 Token 消耗越大，没有裁剪/摘要策略
- ❌ **Summarizer 是占位**：标题和摘要都是简单截取，没有用 LLM 生成
- ❌ **无记忆检索策略**：没有 recency/importance 评分机制，所有历史消息同等对待
- ❌ **无向量化记忆**：所有记忆检索靠 SQL FTS，没有语义搜索

### 9.2 设计方案

#### 9.2.1 新增文件结构

```
app/session_history/
├── __init__.py
├── models.py                 # （已有）新增记忆相关模型
├── service.py                # （已有）集成新能力
├── repository.py             # （已有）
├── search.py                 # （已有）
├── summarizer.py             # ⬆️ 重写：LLM 驱动的摘要生成
├── compressor.py             # 🆕 上下文压缩器
├── memory_retriever.py       # 🆕 记忆检索器（多策略）
└── vector_memory.py          # 🆕 向量化记忆（基于 PGVector）
```

#### 9.2.2 上下文压缩器

```python
# app/session_history/compressor.py

class ContextWindow:
    """上下文窗口 — 管理 Agent 的历史上下文。"""

    max_tokens: int = 128_000          # 上下文窗口上限
    reserve_tokens: int = 32_000       # 为最新内容保留的 Token 数
    compression_strategy: str = "summarize"  # truncate / summarize / rolling

class ContextCompressor:
    """上下文压缩器 — Token 超限时自动压缩。

    压缩策略（按优先级）：
    1. summarize: 对最旧的消息做 LLM 摘要（保留语义）
    2. rolling:   丢弃最旧的消息（保留最新 N 轮）
    3. truncate:  直接截断最早的消息文本
    """

    def __init__(self, llm_gateway=None):
        self.gateway = llm_gateway
        self.strategy_order = ["summarize", "rolling", "truncate"]

    async def compress(
        self,
        messages: list[ChatMessage],
        max_tokens: int = 128_000,
        reserve_for_latest: int = 32_000,
    ) -> list[ChatMessage]:
        """压缩消息列表至 max_tokens 以内。

        策略：
        1. 计算当前总 Token 数
        2. 如果未超限 → 直接返回
        3. 如果超限 → 按策略顺序尝试压缩
        4. 保留最新的 reserve_for_latest Token 不压缩
        """
        total = self._estimate_tokens(messages)
        if total <= max_tokens:
            return messages

        # 分离"可压缩区"（旧消息）和"保护区"（最新消息）
        safe_tokens = 0
        protected: list[ChatMessage] = []
        compressible: list[ChatMessage] = []

        for msg in reversed(messages):
            tokens = self._estimate_tokens([msg])
            if safe_tokens + tokens <= reserve_for_latest:
                protected.insert(0, msg)
                safe_tokens += tokens
            else:
                compressible.insert(0, msg)

        # 对可压缩区依次尝试策略
        for strategy in self.strategy_order:
            compressed = await self._apply_strategy(strategy, compressible, max_tokens - safe_tokens)
            if self._estimate_tokens(compressed) <= max_tokens - safe_tokens:
                return compressed + protected

        # 终极兜底：只保留最后 N 轮
        return protected

    async def _apply_strategy(
        self,
        strategy: str,
        messages: list[ChatMessage],
        budget: int,
    ) -> list[ChatMessage]:
        """应用单一压缩策略。"""
        if strategy == "truncate":
            return self._truncate(messages, budget)
        elif strategy == "rolling":
            return self._rolling(messages, budget)
        elif strategy == "summarize":
            return await self._summarize(messages, budget)
        return messages

    async def _summarize(
        self,
        messages: list[ChatMessage],
        budget: int,
    ) -> list[ChatMessage]:
        """LLM 摘要压缩 — 将旧消息压缩为一段摘要。"""
        if not self.gateway or not messages:
            return messages

        prompt = f"""请将以下对话压缩为一段简洁的摘要，保留关键信息。要求：
- 保留所有决策和结论
- 保留重要的数据/数字
- 保留待办事项
- 摘要长度不超过 {budget // 4} 个 Token

对话内容：
{''.join(f'{m.role}: {m.content[:500]}' for m in messages[:20])}
"""
        try:
            resp = await self.gateway.complete(prompt=prompt, task_type="memory_compress")
            return [ChatMessage(role="system", content=f"[历史摘要] {resp.content}")]
        except Exception:
            return self._rolling(messages, budget)

    def _rolling(self, messages: list[ChatMessage], budget: int) -> list[ChatMessage]:
        """滑动窗口 — 从旧到新丢弃，直到满足预算。"""
        result = []
        tokens = 0
        for msg in reversed(messages):
            msg_tokens = self._estimate_tokens([msg])
            if tokens + msg_tokens <= budget:
                result.insert(0, msg)
                tokens += msg_tokens
            else:
                break
        return result

    @staticmethod
    def _truncate(messages: list[ChatMessage], budget: int) -> list[ChatMessage]:
        """截断 — 直接掐掉最旧消息的文本。"""
        result = []
        tokens = 0
        for msg in reversed(messages):
            # 估算并限制每个消息的文本长度
            text = msg.content
            while text and tokens + len(text) // 4 > budget:
                text = text[:len(text) // 2]
            if text:
                result.insert(0, ChatMessage(role=msg.role, content=text))
                tokens += len(text) // 4
        return result

    @staticmethod
    def _estimate_tokens(messages: list[ChatMessage]) -> int:
        """粗略估算 Token 数（中文字符 ≈ 1.5 token，英文字符 ≈ 0.25 token）。"""
        total = 0
        for msg in messages:
            text = msg.content
            chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
            english = len(text) - chinese
            total += int(chinese * 1.5 + english * 0.25)
        return total
```

#### 9.2.3 记忆检索策略

```python
# app/session_history/memory_retriever.py

@dataclass
class MemoryItem:
    """记忆条目。"""
    id: str
    content: str
    role: str
    timestamp: datetime
    session_id: str
    # 检索评分
    recency_score: float = 0.0      # 时效性（越新越高）
    relevance_score: float = 0.0    # 相关性（与当前 query 的语义匹配度）
    importance_score: float = 0.0   # 重要性（LLM 评定）
    composite_score: float = 0.0    # 综合评分


class MemoryRetriever:
    """记忆检索器 — 多策略融合检索。

    支持三种策略：
    1. Recency（最近优先）— 适用于短期对话
    2. Relevance（语义相关）— 适用于知识问答
    3. Importance（重要优先）— 适用于长期记忆
    4. Hybrid（融合检索）— 三种策略加权融合
    """

    def __init__(self, vector_store=None, llm_gateway=None):
        self.vector_store = vector_store
        self.gateway = llm_gateway

    async def retrieve(
        self,
        query: str,
        session_id: str,
        strategy: str = "hybrid",
        top_k: int = 10,
    ) -> list[MemoryItem]:
        """检索历史记忆。

        Args:
            query: 当前查询。
            session_id: 会话 ID。
            strategy: 检索策略（recency / relevance / importance / hybrid）。
            top_k: 返回数量。

        Returns:
            按综合评分排序的记忆条目。
        """
        # 1. 加载该会话的所有消息
        messages = await self._load_messages(session_id)

        # 2. 按策略评分
        items = []
        for msg in messages:
            item = MemoryItem(
                id=msg.id,
                content=msg.content,
                role=msg.role,
                timestamp=msg.created_at,
                session_id=session_id,
            )
            # 时效性评分
            item.recency_score = self._score_recency(item.timestamp)

            if strategy in ("relevance", "hybrid"):
                item.relevance_score = await self._score_relevance(query, item.content)

            if strategy in ("importance", "hybrid"):
                item.importance_score = await self._score_importance(item.content)

            # 综合评分
            item.composite_score = self._compute_composite(item, strategy)
            items.append(item)

        # 3. 排序返回 Top-K
        items.sort(key=lambda x: x.composite_score, reverse=True)
        return items[:top_k]

    @staticmethod
    def _score_recency(timestamp: datetime) -> float:
        """时效性评分 — 越新越高（指数衰减）。"""
        hours_ago = (datetime.now(UTC) - timestamp).total_seconds() / 3600
        return math.exp(-hours_ago / 24)  # 24 小时半衰期

    async def _score_relevance(self, query: str, content: str) -> float:
        """相关性评分 — 向量语义相似度。"""
        if not self.vector_store:
            # 降级：关键词重叠
            q_words = set(query.lower().split())
            c_words = set(content.lower().split())
            overlap = len(q_words & c_words)
            return overlap / max(len(q_words), 1) if q_words else 0.0
        # 向量相似度
        return await self.vector_store.compute_similarity(query, content)

    async def _score_importance(self, content: str) -> float:
        """重要性评分 — LLM 判断该信息的重要程度。"""
        if not self.gateway:
            return 0.5
        prompt = f"""判断以下信息的重要性（0-1）：
- 0.0: 闲聊、问候
- 0.3: 一般信息
- 0.6: 决策、需求、约束
- 0.8: 用户明确指示的重要信息
- 1.0: 安全/合规相关的关键信息

内容：{content[:300]}
只返回一个 0-1 之间的数字。"""
        try:
            resp = await self.gateway.complete(prompt=prompt, task_type="memory_importance")
            return max(0.0, min(1.0, float(resp.content.strip())))
        except Exception:
            return 0.5

    @staticmethod
    def _compute_composite(item: MemoryItem, strategy: str) -> float:
        """综合评分 — 按策略加权。"""
        weights = {
            "recency":    {"recency": 1.0, "relevance": 0.0, "importance": 0.0},
            "relevance":  {"recency": 0.0, "relevance": 1.0, "importance": 0.0},
            "importance": {"recency": 0.0, "relevance": 0.0, "importance": 1.0},
            "hybrid":     {"recency": 0.3, "relevance": 0.4, "importance": 0.3},
        }
        w = weights.get(strategy, weights["hybrid"])
        return (
            item.recency_score * w["recency"]
            + item.relevance_score * w["relevance"]
            + item.importance_score * w["importance"]
        )
```

#### 9.2.4 集成到 SessionHistoryService

```python
class SessionHistoryService:
    def __init__(self, ...):
        self.compressor = ContextCompressor(llm_gateway=gateway)
        self.memory_retriever = MemoryRetriever(
            vector_store=PGVectorStore(),
            llm_gateway=gateway,
        )

    async def get_relevant_context(
        self,
        session_id: str,
        query: str,
        max_tokens: int = 128_000,
    ) -> list[ChatMessage]:
        """获取会话的相关上下文（含压缩+检索）。

        流程：
        1. 用 MemoryRetriever 检索相关记忆（按综合评分）
        2. 如果超 Token 限制 → ContextCompressor 压缩
        3. 返回压缩后的上下文
        """
        memories = await self.memory_retriever.retrieve(
            query=query, session_id=session_id, strategy="hybrid",
        )
        messages = [ChatMessage(role=m.role, content=m.content) for m in memories]
        return await self.compressor.compress(messages, max_tokens=max_tokens)
```

### 9.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 上下文不超限 | 100 轮对话 → 压缩后 Token 数 ≤ max_tokens |
| 多策略压缩有效 | summarize / rolling / truncate 三种策略按序尝试 |
| 记忆检索按策略排序 | recency 策略 → 最新消息排最前 |
| 混合检索加权正确 | hybrid 策略 → 综合评分 = 0.3*recency + 0.4*relevance + 0.3*importance |
| 向量记忆检索 | PGVector 相似度搜索返回语义相关记忆 |
| Summarizer 用 LLM | 不再简单截取，调用 `gateway.complete()` 生成摘要 |
| 集成到会话服务 | `get_relevant_context()` 返回压缩后的上下文 |

---

## 10. P1：多租户 Prompt 隔离

### 10.1 问题分析

当前所有租户使用同一套硬编码 System Prompt：

```python
# 各 Layer 的 Node 中
SYSTEM_PROMPT = "你是一个架构设计专家..."  # 所有租户都一样
```

问题：
- ❌ 不同企业的 Prompt 需求不同（SaaS 场景必须支持）
- ❌ 没有租户级 Prompt 模板存储和加载
- ❌ Prompt 中无法注入租户特有信息（企业名称、行业、内部术语等）

### 10.2 设计方案

#### 10.2.1 新增文件结构

```
app/auth/prompts/
├── __init__.py
├── manager.py           # PromptManager — 租户 Prompt 管理
├── store.py             # PromptStore — PostgreSQL 持久化
├── models.py            # TenantPrompt 模型
└── renderer.py          # PromptRenderer — 模板渲染（含变量注入）
```

#### 10.2.2 数据模型

```python
# app/auth/prompts/models.py

class TenantPrompt(BaseModel):
    """租户级 Prompt 模板。"""
    id: str
    organization_id: str
    agent_name: str                        # analysis / planning / generation / evaluation
    node_name: str                         # requirement_extractor / pattern_recommend ...
    template: str                          # Jinja2 模板
    variables: dict[str, str] = Field(default_factory=dict)  # 默认变量值
    version: int = 1
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # 变量示例
    # {{ company_name }} — 企业名称
    # {{ industry }}     — 所属行业
    # {{ tech_stack }}   — 常用技术栈
    # {{ internal_terms }} — 内部术语
```

#### 10.2.3 PromptManager

```python
# app/auth/prompts/manager.py

class PromptManager:
    """Prompt 管理器 — 按租户+Agent+Node 加载 Prompt。

    查找优先级：
    1. 租户自定义 Prompt（organization_id + agent_name + node_name）
    2. 租户默认 Prompt（organization_id + agent_name + "*"）
    3. 系统默认 Prompt（硬编码兜底）

    支持变量注入：
    - {{ company_name }} → 从租户配置自动填充
    - {{ industry }} → 从租户配置自动填充
    """

    def __init__(self, store=None):
        self.store = store or PromptStore()
        self.renderer = PromptRenderer()
        self._cache: dict[str, TenantPrompt] = {}    # LRU 缓存
        self._cache_ttl = 300                         # 5 分钟缓存

    async def get_prompt(
        self,
        organization_id: str,
        agent_name: str,
        node_name: str,
        extra_vars: dict[str, str] | None = None,
    ) -> str:
        """获取渲染后的 Prompt。

        Args:
            organization_id: 组织 ID。
            agent_name: Agent 名称。
            node_name: Node 名称。
            extra_vars: 额外变量（覆盖默认值）。

        Returns:
            渲染后的 System Prompt 文本。
        """
        # 1. 查找最精确的匹配
        template = await self._find_template(organization_id, agent_name, node_name)
        if template is None:
            # 2. 回退到系统默认
            return self._get_default_prompt(agent_name, node_name)

        # 3. 合并变量 + 渲染
        variables = {**template.variables, **(extra_vars or {})}
        return self.renderer.render(template.template, variables)

    async def _find_template(
        self,
        org_id: str,
        agent: str,
        node: str,
    ) -> TenantPrompt | None:
        """按优先级查找模板。"""
        cache_key = f"{org_id}:{agent}:{node}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        # 优先级 1: 精确匹配
        template = await self.store.get(org_id, agent, node)
        if template:
            self._cache[cache_key] = template
            return template

        # 优先级 2: Agent 级通配
        template = await self.store.get(org_id, agent, "*")
        if template:
            self._cache[cache_key] = template
            return template

        return None

    async def upsert_template(self, prompt: TenantPrompt) -> None:
        """创建或更新租户 Prompt。"""
        await self.store.upsert(prompt)
        self._cache.clear()  # 清除缓存

    async def delete_template(self, org_id: str, agent: str, node: str) -> bool:
        """删除租户 Prompt（回退到系统默认）。"""
        result = await self.store.delete(org_id, agent, node)
        self._cache.clear()
        return result

    @staticmethod
    def _get_default_prompt(agent: str, node: str) -> str:
        """获取系统默认 Prompt（硬编码兜底）。"""
        # 从各 Layer 目前硬编码的 Prompt 中加载
        DEFAULTS = {
            "analysis:requirement": "你是一个需求分析专家。从以下 PRD 中提取功能需求和非功能需求。",
            "planning:pattern": "你是一个架构设计专家。推荐适合的架构模式。",
            "generation:outline": "你是一个技术文档作者。生成技术方案大纲。",
            "evaluation:scoring": "你是一个技术评审专家。对以下方案进行评分。",
        }
        return DEFAULTS.get(f"{agent}:{node}", "你是一个 AI 助手。")

    def invalidate_cache(self, org_id: str | None = None) -> None:
        """清除缓存（API 更新配置后调用）。"""
        if org_id:
            self._cache = {k: v for k, v in self._cache.items() if not k.startswith(f"{org_id}:")}
        else:
            self._cache.clear()
```

#### 10.2.4 PromptRenderer

```python
# app/auth/prompts/renderer.py

from jinja2 import Template

class PromptRenderer:
    """Prompt 渲染器 — 使用 Jinja2 模板引擎注入变量。"""

    def render(self, template_str: str, variables: dict[str, str]) -> str:
        """渲染 Prompt 模板。

        Args:
            template_str: Jinja2 模板字符串。
            variables: 变量字典。

        Returns:
            渲染后的 Prompt。

        模板示例：
        ```
        你是一个 {{ role }}，为 {{ company_name }}（{{ industry }} 行业）设计技术方案。
        该企业的常用技术栈：{{ tech_stack }}
        内部术语：{{ internal_terms }}
        ```
        """
        template = Template(template_str)
        return template.render(**variables)
```

#### 10.2.5 集成到 Agent Node

```python
# 改造前后对比

# 改造前：硬编码
SYSTEM_PROMPT = "你是一个需求分析专家..."

# 改造后：从 PromptManager 加载
class RequirementExtractorNode:
    async def run(self, state: AnalysisState) -> AnalysisState:
        prompt = await prompt_manager.get_prompt(
            organization_id=state.get("tenant_context", {}).get("organization_id", ""),
            agent_name="analysis",
            node_name="requirement",
            extra_vars={
                "company_name": state.get("tenant_context", {}).get("settings", {}).get("company_name", ""),
                "industry": state.get("tenant_context", {}).get("settings", {}).get("industry", ""),
            },
        )
        # 将 system prompt 传给 LLM
        resp = await gateway.complete(
            prompt=user_prompt,
            system_prompt=prompt,  # ← 租户隔离的 system prompt
            task_type="analysis_requirement",
        )
        ...
```

### 10.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 租户 A 的 Prompt 不影响租户 B | 两个租户同时调用同一 Node → 返回各自的 Prompt |
| 三级回退生效 | 删除租户自定义 Prompt → 自动用系统默认 |
| 变量注入正确 | `{{ company_name }}` 被替换为实际企业名 |
| 缓存生效 | 相同查询 5 分钟内不走数据库 |
| API 更新后缓存清除 | `PUT /api/v1/org/prompts` → `invalidate_cache()` |

---

## 11. P2：Prompt 版本管理

### 11.1 问题分析

所有 Prompt 是代码内的硬编码字符串，问题：
- ❌ 没有版本号，改了不知道改了什么
- ❌ 无法回滚（改坏了只能 git revert）
- ❌ 无法做 A/B 测试（不能同时跑新旧两个 Prompt）

### 11.2 设计方案

#### 11.2.1 新增文件结构

```
app/core/prompt_registry/
├── __init__.py
├── registry.py          # PromptRegistry — 版本注册器
├── models.py            # PromptVersion 模型
├── storage.py           # 数据库持久化
└── ab_test.py           # A/B 测试路由
```

#### 11.2.2 核心模型

```python
# app/core/prompt_registry/models.py

class PromptVersion(BaseModel):
    """Prompt 版本。"""
    id: str
    name: str                              # "analysis.requirement"
    version: int                           # 自增版本号
    content: str                           # Prompt 文本
    hash: str                              # SHA-256 内容哈希
    author: str = ""                        # 修改人
    changelog: str = ""                     # 变更说明
    is_active: bool = False                 # 是否当前激活版本
    tags: list[str] = Field(default_factory=list)  # 标签（如 "experiment", "stable"）
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ABTestConfig(BaseModel):
    """A/B 测试配置。"""
    prompt_name: str
    version_a: int
    version_b: int
    traffic_split: float = 0.5             # A 版本流量占比
    metric: str = "eval_score"             # 对比指标
    is_active: bool = False
```

#### 11.2.3 PromptRegistry

```python
# app/core/prompt_registry/registry.py

class PromptRegistry:
    """Prompt 版本注册器 — 版本化+回滚+A/B 测试。

    每个 Prompt 有独立的版本历史：
    - 版本号自动递增
    - 内容哈希防篡改
    - 支持任意版本回滚
    """

    def __init__(self, storage=None):
        self.storage = storage or PromptStorage()
        self._active_cache: dict[str, PromptVersion] = {}

    async def register(
        self,
        name: str,
        content: str,
        author: str = "",
        changelog: str = "",
        tags: list[str] | None = None,
    ) -> PromptVersion:
        """注册新版本。

        Args:
            name: Prompt 名称（如 "analysis.requirement"）。
            content: Prompt 文本。
            author: 修改人。
            changelog: 变更说明。
            tags: 标签。

        Returns:
            创建的 PromptVersion。

        Raises:
            DuplicateHashError: 内容与上一版完全相同时抛出。
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # 获取当前最新版本
        latest = await self.storage.get_latest(name)

        # 检查内容是否重复
        if latest and latest.hash == content_hash:
            raise DuplicateHashError(name, content_hash)

        version = (latest.version + 1) if latest else 1

        # 旧版本取消激活
        if latest and latest.is_active:
            await self.storage.deactivate(name)

        pv = PromptVersion(
            id=str(uuid.uuid4()),
            name=name,
            version=version,
            content=content,
            hash=content_hash,
            author=author,
            changelog=changelog,
            is_active=True,
            tags=tags or [],
        )
        await self.storage.save(pv)
        self._active_cache[name] = pv
        return pv

    async def get_active(self, name: str) -> PromptVersion:
        """获取当前激活版本。"""
        # 优先查缓存
        cached = self._active_cache.get(name)
        if cached:
            return cached
        # 查数据库
        pv = await self.storage.get_active(name)
        if pv is None:
            raise PromptNotFoundError(name)
        self._active_cache[name] = pv
        return pv

    async def rollback(self, name: str, version: int) -> PromptVersion:
        """回滚到指定版本。"""
        # 1. 查找目标版本
        target = await self.storage.get_version(name, version)
        if target is None:
            raise VersionNotFoundError(name, version)
        # 2. 取消当前激活
        await self.storage.deactivate(name)
        # 3. 激活目标版本
        target.is_active = True
        target.version = await self.storage.get_next_version(name)  # 新版本号
        target.changelog = f"回滚到 v{version}"
        await self.storage.save(target)
        self._active_cache[name] = target
        return target

    async def get_history(self, name: str, limit: int = 20) -> list[PromptVersion]:
        """获取版本历史。"""
        return await self.storage.get_history(name, limit=limit)

    async def diff(self, name: str, v1: int, v2: int) -> str:
        """对比两个版本的差异（类 git diff）。"""
        pv1 = await self.storage.get_version(name, v1)
        pv2 = await self.storage.get_version(name, v2)
        if not pv1 or not pv2:
            raise VersionNotFoundError(name)
        # 简单的逐行 diff
        lines1 = pv1.content.splitlines()
        lines2 = pv2.content.splitlines()
        import difflib
        return "\n".join(difflib.unified_diff(lines1, lines2, f"v{v1}", f"v{v2}"))

    async def resolve_ab_test(self, name: str, user_id: str) -> PromptVersion:
        """A/B 测试路由 — 根据用户 ID 哈希决定走哪个版本。"""
        config = await self.storage.get_ab_config(name)
        if not config or not config.is_active:
            return await self.get_active(name)

        # 一致性哈希：同一用户始终走同一版本
        user_hash = (hash(user_id) % 100) / 100.0
        if user_hash < config.traffic_split:
            return await self.storage.get_version(name, config.version_a)
        else:
            return await self.storage.get_version(name, config.version_b)
```

#### 11.2.4 API 端点

```python
# 新增 API 路由

@router.post("/api/v1/prompts/register")
async def register_prompt(name: str, content: str, author: str, changelog: str):
    """注册新 Prompt 版本。"""
    pv = await prompt_registry.register(name, content, author, changelog)
    return {"version": pv.version, "hash": pv.hash}

@router.post("/api/v1/prompts/{name}/rollback")
async def rollback_prompt(name: str, version: int):
    """回滚 Prompt 到指定版本。"""
    pv = await prompt_registry.rollback(name, version)
    return {"new_version": pv.version, "rolled_back_to": version}

@router.get("/api/v1/prompts/{name}/history")
async def get_prompt_history(name: str, limit: int = 20):
    """获取版本历史。"""
    return await prompt_registry.get_history(name, limit)

@router.get("/api/v1/prompts/{name}/diff")
async def diff_prompt(name: str, v1: int, v2: int):
    """对比两个版本差异。"""
    return await prompt_registry.diff(name, v1, v2)

@router.post("/api/v1/prompts/ab-test")
async def create_ab_test(config: ABTestConfig):
    """创建 A/B 测试。"""
    ...
```

### 11.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 注册新版本自动递增 | 第 1 次注册 → v1，第 2 次 → v2 |
| 回滚到旧版本 | `rollback("x", 1)` → 当前激活为 v1 的内容，版本号为 v3 |
| 版本历史可查 | `get_history("x")` 返回 [v3, v2, v1] |
| 版本对比 | `diff("x", 1, 2)` 输出 unified diff |
| A/B 测试路由 | 用户 A 走 v1，用户 B 走 v2（一致哈希） |
| 内容重复检测 | 相同内容重复注册 → 抛 `DuplicateHashError` |

---

## 12. P2：Agent 行为回放

### 12.1 问题分析

当前可观测性只能看实时指标，但：
- ❌ 出问题了不能回放 Agent 的决策过程
- ❌ 不知道某个 Node 为什么做出某个决定
- ❌ 调试复杂 Agent 行为全靠加日志

### 12.2 设计方案

#### 12.2.1 新增文件结构

```
app/observability/replay/
├── __init__.py
├── recorder.py           # DecisionRecorder — 决策记录器
├── models.py             # 回放数据模型
├── player.py             # ReplayPlayer — 回放播放器
└── analyzer.py           # DecisionAnalyzer — 决策分析
```

#### 12.2.2 决策记录模型

```python
# app/observability/replay/models.py

class DecisionRecord(BaseModel):
    """单次决策记录。"""
    id: str
    task_id: str
    trace_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # 执行上下文
    agent_name: str                    # analysis / planning / generation / evaluation
    node_name: str                     # requirement_extractor / pattern_recommend ...
    iteration_count: int = 0

    # 输入
    input_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_prompt: str = ""             # 发给 LLM 的完整 Prompt
    input_tools: list[dict] = Field(default_factory=list)  # 可用的工具

    # 输出
    llm_response: str = ""             # LLM 的原始返回
    tool_calls: list[dict] = Field(default_factory=list)   # LLM 选择的工具
    tool_results: list[dict] = Field(default_factory=list)  # 工具执行结果
    output_state_diff: dict[str, Any] = Field(default_factory=dict)  # 执行前后的 State 变化

    # 性能
    duration_ms: float = 0.0
    tokens_consumed: int = 0

    # 决策总结（LLM 生成）
    decision_summary: str = ""         # "从 PRD 中提取了 5 个需求，调用 search_knowledge 获取了上下文"

class TraceTree(BaseModel):
    """全链路追踪树 — 一个 task 的完整决策链。"""
    task_id: str
    start_time: datetime
    end_time: datetime | None = None
    total_duration_ms: float = 0.0
    nodes: list[DecisionRecord] = Field(default_factory=list)
    edges: list[tuple[str, str, str]] = Field(default_factory=list)  # (from_node_id, to_node_id, label)
```

#### 12.2.3 DecisionRecorder

```python
# app/observability/replay/recorder.py

class DecisionRecorder:
    """决策记录器 — 记录 Agent 每一步的完整决策过程。

    记录内容：
    - LLM 输入（完整 Prompt）
    - LLM 输出（原始响应 + Tool Calls）
    - State 变化（执行前后的 diff）
    - 性能数据（耗时、Token 消耗）
    """

    def __init__(self, storage=None):
        self.storage = storage or ReplayStorage()
        self._current_trace: dict[str, TraceTree] = {}

    async def start_trace(self, task_id: str) -> None:
        """开始追踪一个新任务。"""
        self._current_trace[task_id] = TraceTree(
            task_id=task_id,
            start_time=datetime.now(UTC),
        )

    async def record_decision(
        self,
        task_id: str,
        agent_name: str,
        node_name: str,
        input_state: dict,
        input_prompt: str,
        input_tools: list[dict],
        llm_response: str,
        tool_calls: list[dict],
        tool_results: list[dict],
        output_state: dict,
        duration_ms: float,
        tokens: int,
    ) -> DecisionRecord:
        """记录一次 Node 执行。"""
        record = DecisionRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            trace_id=task_id,
            agent_name=agent_name,
            node_name=node_name,
            input_state_snapshot=self._summarize_state(input_state),
            input_prompt=self._truncate_prompt(input_prompt),
            input_tools=input_tools,
            llm_response=llm_response,
            tool_calls=tool_calls,
            tool_results=tool_results,
            output_state_diff=self._compute_diff(input_state, output_state),
            duration_ms=duration_ms,
            tokens_consumed=tokens,
        )

        # 追加到追踪树
        trace = self._current_trace.get(task_id)
        if trace:
            trace.nodes.append(record)
            if len(trace.nodes) > 1:
                prev = trace.nodes[-2]
                trace.edges.append((prev.id, record.id, agent_name))
                # 用 LLM 生成决策摘要（异步，不阻塞）
                asyncio.create_task(self._summarize_decision(record))

        await self.storage.save(record)
        return record

    async def end_trace(self, task_id: str) -> TraceTree:
        """结束追踪并保存完整链路。"""
        trace = self._current_trace.pop(task_id, None)
        if trace:
            trace.end_time = datetime.now(UTC)
            trace.total_duration_ms = (
                trace.end_time - trace.start_time
            ).total_seconds() * 1000
            await self.storage.save_trace(trace)
        return trace

    @staticmethod
    def _compute_diff(before: dict, after: dict) -> dict[str, Any]:
        """计算 State 的变化（只保留变化字段）。"""
        diff = {}
        for key in after:
            if key not in before or before[key] != after[key]:
                # 只记录类型和大小，不记录完整值（避免存储爆炸）
                val = after[key]
                if isinstance(val, (list, dict)):
                    diff[key] = {"type": type(val).__name__, "size": len(val), "changed": True}
                else:
                    diff[key] = val
        return diff

    @staticmethod
    def _truncate_prompt(prompt: str, max_len: int = 2000) -> str:
        """截断过长的 Prompt（只保留前后文）。"""
        if len(prompt) <= max_len:
            return prompt
        half = max_len // 2
        return prompt[:half] + "\n...(中间省略)...\n" + prompt[-half:]

    @staticmethod
    def _summarize_state(state: dict) -> dict[str, Any]:
        """摘要化 State（避免记录完整的大对象）。"""
        summary = {}
        for key, val in state.items():
            if isinstance(val, str) and len(val) > 200:
                summary[key] = val[:200] + "..."
            elif isinstance(val, list):
                summary[key] = f"[{type(val).__name__}:{len(val)}]"
            else:
                summary[key] = val
        return summary

    async def _summarize_decision(self, record: DecisionRecord) -> None:
        """用 LLM 生成人类可读的决策摘要。"""
        try:
            from app.llm_gateway import gateway
            prompt = f"""总结以下 Agent 决策过程（一句话）：
Agent: {record.agent_name}
Node: {record.node_name}
LLM 输入: {record.input_prompt[:200]}
LLM 输出: {record.llm_response[:200]}
调用的工具: {[tc.get('function',{}).get('name','') for tc in record.tool_calls]}
"""
            resp = await gateway.complete(prompt=prompt, task_type="decision_summary", max_tokens=100)
            record.decision_summary = resp.content
        except Exception:
            record.decision_summary = f"{record.agent_name}.{record.node_name}"
```

#### 12.2.4 ReplayPlayer

```python
# app/observability/replay/player.py

class ReplayPlayer:
    """回放播放器 — 按时间线重演 Agent 的决策过程。"""

    async def get_trace(self, task_id: str) -> TraceTree:
        """获取任务的完整决策链。"""
        return await self.storage.get_trace(task_id)

    async def replay_step(self, task_id: str, step_index: int) -> DecisionRecord:
        """回放单步决策。"""
        trace = await self.get_trace(task_id)
        if not trace or step_index >= len(trace.nodes):
            raise StepNotFoundError(task_id, step_index)
        return trace.nodes[step_index]

    async def export_replay(self, task_id: str, format: str = "markdown") -> str:
        """导出回放报告（用于复盘）。"""
        trace = await self.get_trace(task_id)
        if not trace:
            return ""

        if format == "markdown":
            return self._to_markdown(trace)
        elif format == "json":
            return trace.model_dump_json(indent=2)
        return str(trace)

    @staticmethod
    def _to_markdown(trace: TraceTree) -> str:
        """导出 Markdown 格式的回放报告。"""
        lines = [
            f"# Agent 行为回放报告",
            f"",
            f"**任务 ID**: {trace.task_id}",
            f"**开始时间**: {trace.start_time.isoformat()}",
            f"**结束时间**: {trace.end_time.isoformat() if trace.end_time else '进行中'}",
            f"**总耗时**: {trace.total_duration_ms:.0f}ms",
            f"**决策步数**: {len(trace.nodes)}",
            f"",
            f"---",
            f"",
        ]
        for i, node in enumerate(trace.nodes):
            lines.extend([
                f"## 第 {i + 1} 步：{node.agent_name}.{node.node_name}",
                f"",
                f"**耗时**: {node.duration_ms:.0f}ms | **Token**: {node.tokens_consumed}",
                f"**摘要**: {node.decision_summary}",
                f"",
                f"### LLM 输入（截取）",
                f"```",
                f"{node.input_prompt[:500]}",
                f"```",
                f"",
                f"### LLM 输出",
                f"```",
                f"{node.llm_response[:500]}",
                f"```",
                f"",
            ])
            if node.tool_calls:
                lines.extend([
                    f"### 工具调用",
                    f"```json",
                    f"{json.dumps(node.tool_calls, indent=2, ensure_ascii=False)}",
                    f"```",
                    f"",
                ])
            lines.append(f"---")
            lines.append(f"")

        return "\n".join(lines)
```

#### 12.2.5 集成到 TracingMiddleware

```python
# 在 observability/tracing.py 中扩展

class TracingMiddleware:
    def __init__(self):
        self.recorder = DecisionRecorder()

    def wrap_node(self, node_fn, node_name):
        @functools.wraps(node_fn)
        def traced_node(*args, **kwargs):
            state = args[0] if args else kwargs.get("state", {})
            task_id = state.get("task_id", "")

            with tracer.start_as_current_span(f"node.{node_name}") as span:
                start = time.monotonic()
                try:
                    # 记录输入
                    input_state = deepcopy(state) if isinstance(state, dict) else {}

                    result = node_fn(*args, **kwargs)

                    # 记录决策
                    asyncio.create_task(
                        self.recorder.record_decision(
                            task_id=task_id,
                            agent_name=state.get("current_layer", ""),
                            node_name=node_name,
                            input_state=input_state,
                            input_prompt=state.get("_last_prompt", ""),
                            input_tools=state.get("_last_tools", []),
                            llm_response=state.get("_last_llm_response", ""),
                            tool_calls=state.get("_last_tool_calls", []),
                            tool_results=state.get("_last_tool_results", []),
                            output_state=result if isinstance(result, dict) else {},
                            duration_ms=(time.monotonic() - start) * 1000,
                            tokens=span.attributes.get("tokens", 0),
                        )
                    )
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    raise

        return traced_node
```

### 12.3 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 每步决策可回放 | `replay_step(task_id, 0)` 返回第 1 步的完整决策记录 |
| 全链路追踪树 | `get_trace(task_id)` 返回所有 Node 的树状结构 |
| 回放报告可导出 | `export_replay(task_id, "markdown")` 输出 Markdown 报告 |
| 决策摘要可读 | 每个 Node 有 `decision_summary` 字段 |
| 性能影响可控 | 启用录制 vs 不启用 → 延迟增加 < 5% |
| 存储控制 | 自动清理 7 天前的回放数据 |

---

## 13. P1：意图驱动的任务路由

### 13.1 问题分析

当前（整改前）所有用户输入走同一入口 `POST /api/v1/generate`（整改后已被 `/api/v1/interact` 统一入口替代），无论什么问题都走完整 4 层 Orchestrator：

```
用户输入 "微服务有哪些组件？"   → Orchestrator 全链路（Analysis→Planning→Generation→Evaluation）
用户输入 "生成完整的技术方案"   → Orchestrator 全链路（同样流程）
```

问题：
- ❌ 简单问答（查文档、问概念）也走全链路，浪费 Token 和时间（等 10s+ 才能回答一个简单问题）
- ❌ 没有意图分类器，无法自动区分"对话"、"知识查询"、"复杂生成"
- ❌ 客户端必须手动选择端点（`/generate` vs `/qna/stream`，整改后已收敛为单一 `/interact`），用户体验差

### 13.2 设计方案

#### 13.2.1 统一入口 + 自动分流

```
客户端
  │
  POST /api/v1/interact  ← 唯一统一入口（整改后实现）
  │
  ▼
┌─────────────────────────────────────┐
│ IntentClassifier                     │  ← 自动判断任务类型
│                                      │
│  输入：用户消息 + 会话历史(可选)      │
│  输出：{intent, confidence, params}  │
└──────────┬──────────────────────────┘
           │
      ┌────┼────────────┐
      ▼    ▼            ▼
  ┌─────┐ ┌──────┐ ┌──────────┐
  │对话  │ │知识查询│ │复杂生成   │
  │Chat  │ │QA     │ │Generate  │
  └──┬──┘ └──┬───┘ └─────┬────┘
     │       │           │
     ▼       ▼           ▼
  流式回答   检索+流式回答  SSE 全链路
```

#### 13.2.2 IntentClassifier

```python
# 新增：app/orchestrator/intent_classifier.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class IntentType(StrEnum):
    """任务意图类型。"""
    CHAT = "chat"               # 纯对话（闲聊、问候、普通交流）
    KNOWLEDGE_QA = "knowledge_qa"   # 知识查询（查文档、问概念、搜代码）
    COMPLEX_GENERATION = "complex_generation"  # 复杂生成（PRD→TSD、技术方案）
    CLARIFICATION = "clarification"  # 需要更多信息（歧义输入）


@dataclass
class IntentResult:
    """意图分类结果。"""
    intent: IntentType
    confidence: float                    # 置信度 0.0 ~ 1.0
    sub_intent: str = ""                 # 子意图（如 "search_doc", "ask_concept"）
    params: dict = field(default_factory=dict)  # 额外参数
    explanation: str = ""                # 分类理由（用于调试和日志）


class IntentClassifier:
    """意图分类器 — 自动判断用户输入的任务类型。

    两级策略：
    1. 规则匹配（关键词 + 模式）— 快路径，无需 LLM
    2. LLM 分类（规则不确定时）— 准确路径，调用轻量模型
    """

    def __init__(self, llm_gateway=None):
        self._llm_gateway = llm_gateway

    # ── 规则层 ──

    # 问候/闲聊关键词
    CHAT_PATTERNS = [
        "你好", "嗨", "hello", "hi", "hey",
        "再见", "拜拜", "bye",
        "谢谢", "感谢", "thanks", "thank you",
        "?", "？",                           # 纯问号结尾可能是简单问题
    ]

    # 知识查询关键词
    KNOWLEDGE_PATTERNS = [
        "是什么", "什么是", "有哪些", "哪个",
        "怎么", "如何", "怎样",
        "有没有", "是否存在",
        "解释一下", "说明一下",
        "what is", "how to", "how do",
        "search", "find", "look up",
        "文档", "文件", "文档中",
        "知识库", "知识图谱",
    ]

    # 复杂生成关键词
    GENERATION_PATTERNS = [
        "生成", "创建", "编写", "撰写",
        "设计", "设计方案", "技术方案",
        "写文档", "生成文档",
        "generate", "create", "design",
        "技术规格", "TSD", "PRD",
    ]

    async def classify(
        self,
        user_input: str,
        session_history: list[dict] | None = None,
    ) -> IntentResult:
        """分类用户输入。

        Args:
            user_input: 用户输入文本。
            session_history: 当前会话历史（可选，用于上下文判断）。

        Returns:
            意图分类结果。
        """
        input_lower = user_input.lower().strip()

        # Stage 1: 规则匹配（快路径）
        rule_result = self._rule_based(input_lower)
        if rule_result and rule_result.confidence >= 0.8:
            return rule_result

        # Stage 2: LLM 分类（规则不确定时）
        if self._llm_gateway:
            llm_result = await self._llm_classify(user_input, session_history)
            if llm_result.confidence > rule_result.confidence if rule_result else 0.5:
                return llm_result

        # 兜底：返回规则结果（即使置信度低）
        return rule_result or IntentResult(
            intent=IntentType.COMPLEX_GENERATION,
            confidence=0.5,
            explanation="规则和 LLM 均无法确定，默认走复杂生成",
        )

    def _rule_based(self, input_lower: str) -> IntentResult | None:
        """基于规则的快速分类。

        规则优先级：CHAT < KNOWLEDGE_QA < COMPLEX_GENERATION
        （匹配多种时取优先级最高的）
        """
        # 检查是否匹配生成模式（最高优先级）
        for pattern in self.GENERATION_PATTERNS:
            if pattern in input_lower:
                return IntentResult(
                    intent=IntentType.COMPLEX_GENERATION,
                    confidence=0.85,
                    sub_intent="pattern_generation",
                    explanation=f"匹配生成关键词: {pattern}",
                )

        # 检查是否匹配知识查询模式
        knowledge_match_count = 0
        for pattern in self.KNOWLEDGE_PATTERNS:
            if pattern in input_lower:
                knowledge_match_count += 1
        if knowledge_match_count >= 2:
            return IntentResult(
                intent=IntentType.KNOWLEDGE_QA,
                confidence=0.9,
                sub_intent="multi_pattern_qa",
                explanation=f"匹配 {knowledge_match_count} 个知识查询关键词",
            )
        if knowledge_match_count == 1:
            return IntentResult(
                intent=IntentType.KNOWLEDGE_QA,
                confidence=0.7,
                sub_intent="single_pattern_qa",
                explanation="匹配 1 个知识查询关键词",
            )

        # 检查是否匹配闲聊模式
        for pattern in self.CHAT_PATTERNS:
            if pattern in input_lower:
                return IntentResult(
                    intent=IntentType.CHAT,
                    confidence=0.8,
                    explanation=f"匹配闲聊关键词: {pattern}",
                )

        # 短查询（< 8 字）倾向于知识查询
        if len(input_lower) < 8:
            return IntentResult(
                intent=IntentType.KNOWLEDGE_QA,
                confidence=0.6,
                sub_intent="short_query",
                explanation="短查询，倾向于知识检索",
            )

        return None

    async def _llm_classify(
        self,
        user_input: str,
        session_history: list[dict] | None = None,
    ) -> IntentResult:
        """使用 LLM 进行意图分类。"""
        if not self._llm_gateway:
            return IntentResult(intent=IntentType.COMPLEX_GENERATION, confidence=0.5)

        # 构建分类 prompt
        history_context = ""
        if session_history:
            recent = session_history[-3:]  # 最近 3 轮
            history_context = "最近对话：\n" + "\n".join(
                f"{m.get('role','')}: {m.get('content','')[:200]}"
                for m in recent
            )

        prompt = f"""分析用户输入的任务类型，只返回 JSON：

{history_context}

用户输入：{user_input}

可选类型：
1. chat — 纯对话（问候、闲聊、感谢、简单交流）
2. knowledge_qa — 知识查询（查找文档、问概念、技术问题、"有没有"类问题）
3. complex_generation — 复杂生成（生成文档、设计方案、技术方案、写代码）
4. clarification — 需要澄清（输入模糊、歧义）

返回格式：
{{"intent": "类型名", "confidence": 0.0~1.0, "reason": "判断理由"}}
"""
        try:
            resp = await self._llm_gateway.complete(
                prompt=prompt,
                task_type="intent_classify",
                temperature=0.1,
                max_tokens=200,
            )
            import json
            data = json.loads(resp.content)
            intent_str = data.get("intent", "complex_generation")
            # 验证 intent 是否合法
            try:
                intent = IntentType(intent_str)
            except ValueError:
                intent = IntentType.COMPLEX_GENERATION

            return IntentResult(
                intent=intent,
                confidence=float(data.get("confidence", 0.7)),
                explanation=data.get("reason", ""),
            )
        except Exception:
            return IntentResult(
                intent=IntentType.COMPLEX_GENERATION,
                confidence=0.5,
                explanation="LLM 分类失败，默认走复杂生成",
            )
```

#### 13.2.3 统一 Chat 路由

```python
# 新增：app/api/routes/chat.py

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.orchestrator.intent_classifier import (
    IntentClassifier,
    IntentType,
)

router = APIRouter(prefix="/api/v1")


class ChatRequest(BaseModel):
    """统一聊天请求。"""
    message: str
    session_id: str = ""          # 关联会话（用于历史消息加载）
    workspace_id: str = ""


@router.post("/interact")
async def interact(req: InteractRequest, ...):
    """统一入口 — 自动分流到对应处理器。

    不做：用户手动选端点（整改后统一为 /interact，由意图识别自动分流）。
    做：服务端自动判断意图，路由到正确路径。
    """
    # 1. 加载会话历史（如果有）
    history = None
    if req.session_id:
        history = await session_service.get_messages(req.session_id)

    # 2. 意图分类
    classifier = IntentClassifier(llm_gateway=gateway)
    intent = await classifier.classify(req.message, history)

    # 3. 自动路由
    if intent.intent == IntentType.CHAT:
        return EventSourceResponse(
            ChatStreamer().stream(req.message, history)
        )

    elif intent.intent == IntentType.KNOWLEDGE_QA:
        return EventSourceResponse(
            QAStreamer().stream(
                query=req.message,
                workspace_id=req.workspace_id,
                history=history,
            )
        )

    elif intent.intent == IntentType.COMPLEX_GENERATION:
        # 创建异步任务 + 返回 SSE 流
        task_id = await task_manager.create_task(...)
        return EventSourceResponse(
            GenerationStreamer().stream(task_id)
        )

    elif intent.intent == IntentType.CLARIFICATION:
        return EventSourceResponse(
            ClarificationStreamer().stream(req.message)
        )
```

#### 13.2.4 三种路径对比

| 路径 | 意图类型 | 流程 | 耗时 |
|------|---------|------|------|
| **Chat** | `chat` | LLM 直接回答（流式） | ~1-3s |
| **Knowledge QA** | `knowledge_qa` | 知识检索 → LLM 回答（流式） | ~2-5s |
| **Complex Generation** | `complex_generation` | 知识检索 → Analysis → Planning → Generation(流式) → Evaluation | ~30-120s |

#### 13.2.5 会话中意图切换

同一会话内允许意图切换——用户先问了个简单问题（Knowledge QA），然后说"把这个写成技术方案"（Complex Generation）：

```
用户: "微服务有哪些组件？"
  → IntentClassifier → knowledge_qa → 检索+流式回答

用户: "把这个结果写成正式的技术方案文档"
  → IntentClassifier → complex_generation → 走全链路
  → 把上一条知识检索结果作为上下文注入
```

实现要点：`IntentClassifier.classify()` 每次独立判断，不受之前结果影响。

#### 13.2.6 会话历史注入

Knowledge QA 和 Chat 路径中，历史消息通过 MemoryRetriever 加载：

```python
class QAStreamer(BaseStreamer):
    async def stream(self, query: str, workspace_id: str, history: list | None = None):
        # 如果有历史会话，先检索相关上下文
        relevant_context = ""
        if history:
            retriever = MemoryRetriever(...)
            memories = await retriever.retrieve(
                query=query,
                messages=history,
                strategy="hybrid",
            )
            relevant_context = self._format_memories(memories)

        # 构建含上下文的 Prompt
        prompt = f"{relevant_context}\n\n用户问题：{query}"
        ...
```

### 13.3 新增文件结构

```
app/orchestrator/
├── __init__.py
├── main_graph.py              # （已有）
├── intent_classifier.py       # 🆕 IntentClassifier + IntentType
└── ...

app/api/routes/
├── interact.py               # 🆕 POST /api/v1/interact（统一入口）
├── stream_generate.py        # （已有）保留：/tasks/{id}/events + /tasks/{id}/stream-review
└── ...
```

### 13.4 与 SSE 的关系

```
POST /api/v1/interact
  → IntentClassifier.classify()
    ├─ chat           → ChatStreamer（§17 新增）
    ├─ knowledge_qa   → QAStreamer（§17.2.7）
    ├─ complex_generation → GenerationStreamer（§17.2.5）
    └─ clarification  → ClarificationStreamer（§17 新增）
```

意图分类器是 **SSE 流式架构的上游调度器**，客户端只需调用 `POST /api/v1/interact`，不需要知道后端路由逻辑。

### 13.5 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 问候分流到 Chat | 输入"你好" → `intent=chat`，不走知识检索和生成 |
| 知识查询分流到 QA | 输入"微服务有哪些组件" → `intent=knowledge_qa`，走检索+流式回答 |
| 复杂生成分流到 Generate | 输入"生成完整的技术方案" → `intent=complex_generation`，走全链路 |
| LLM 分类兜底 | 规则不确定时 → 调 LLM 分类（置信度 > 规则结果时采用） |
| 会话内意图切换 | 先问"有什么文档" → 再说"写成方案" → 正确切换路径 |
| 规则+LLM 双保险 | LLM 不可用时 → 纯规则分类不崩溃 |
| 统一入口可用 | `POST /api/v1/interact` 返回 SSE 流，客户端无需选择端点 |

---

### 17.1 问题分析

当前流程是全异步任务 + 轮询：

```
POST /api/v1/interact（complex_generation）→ task_id → 等 30s+ → GET /tasks/{id} → 完整结果
```

问题：
- ❌ 用户长时间看到 loading，不知道进度（Analysis 到哪了？卡在 Planning 了？）
- ❌ 需要用户介入时（Human-in-the-Loop）需要另开接口轮询
- ❌ 不支持逐 token 流式展示文档，体验差
- ❌ 简单问答也要走异步任务，太重

配合 §13 的 IntentClassifier 自动分流，为每种意图类型提供对应的 SSE 流式处理器。

需要设计一个**统一的 SSE 事件流**，覆盖三种交互场景：

```
场景 A（复杂生成）：loading(进度) → 等待用户决策 → 流式生成文档 → 完成
场景 B（简单问答）：直接流式输出回答 → 完成
场景 C（人工介入）：暂停 → 推送问题 → 等待用户响应 → 继续流式
```

### 17.2 设计方案

#### 17.2.1 SSE 事件协议

```python
# app/api/sse/events.py — 新增

@dataclass
class SSEEvent:
    """SSE 事件 — 所有事件类型的基类。"""
    event: str       # 事件名（客户端根据事件名做不同处理）
    data: Any        # 事件数据
    id: str = ""     # 事件 ID（客户端可以断线重连时传 last-event-id）

class SSEEventType:
    """事件类型常量。"""
    # ── 进度事件（所有阶段通用）──
    STAGE_START = "stage_start"          # data: {"stage": "analysis", "label": "需求分析"}
    STAGE_PROGRESS = "stage_progress"    # data: {"stage": "analysis", "node": "requirement_extractor", "progress": 0.3}
    STAGE_COMPLETE = "stage_complete"    # data: {"stage": "analysis", "duration_ms": 3200}

    # ── 人工介入事件 ──
    HUMAN_REVIEW = "human_review"        # data: {"stage": "planning", "question": "请确认架构方案", "options": [...], "review_id": "xxx"}
    HUMAN_RESPONSE = "human_response"    # 客户端 → 服务端：{"review_id": "xxx", "decision": "approved", "comment": "..."}

    # ── 生成事件 ──
    TOKEN = "token"                      # data: {"text": "## 架构", "index": 0}  逐 token
    TOKEN_DONE = "token_done"            # data: {"total_tokens": 1523}

    # ── 问答事件 ──
    ANSWER_TOKEN = "answer_token"        # data: {"text": "是的"}  逐 token
    ANSWER_DONE = "answer_done"          # data: {"sources": [...]}

    # ── 异常事件 ──
    ERROR = "error"                      # data: {"code": "RATE_LIMITED", "message": "请求过于频繁"}
    WARNING = "warning"                  # data: {"message": "知识检索结果不足，已使用搜索引擎回退"}

    # ── 完成事件 ──
    COMPLETE = "complete"                # data: {"task_id": "xxx", "duration_ms": 45000}
```

SSE 传输格式：

```
event: stage_start
data: {"stage":"analysis","label":"需求分析","task_id":"xxx"}

event: stage_progress
data: {"stage":"analysis","node":"requirement_extractor","progress":0.2}

event: stage_complete
data: {"stage":"analysis","duration_ms":3200}

event: human_review
data: {"stage":"planning","question":"请确认推荐的架构模式是否合适","options":["通过","需要修改"],"review_id":"rev_001"}

# —— 等待客户端发 POST /api/v1/review/rev_001 响应 ——

event: token
data: {"text":"## 系统架构","index":0}

event: token
data: {"text":"\n\n本系统采用","index":1}

event: complete
data: {"task_id":"xxx","duration_ms":45200}
```

#### 17.2.2 统一 SSE 端点

```python
# app/api/routes/stream.py — 新增

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/v1")


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str, last_event_id: str = ""):
    """SSE 事件流端点 — 统一分派到不同处理器。

    根据 task_type 自动选择：
    - "generate" → GenerationStreamer（复杂生成：进度→人工→流式）
    - "qa"       → QAStreamer（简单问答：直接流式）
    """
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    streamer = StreamerRouter.get_streamer(task.type)
    return EventSourceResponse(streamer.stream(task_id, last_event_id))


@router.post("/tasks/{task_id}/review")
async def respond_review(task_id: str, body: ReviewResponse):
    """人工介入响应 — 通过 SSE 恢复流程。

    客户端通过此接口回复人工审核问题，
    服务端将响应推入 task 的 review_channel，
    Orchestrator 的 HumanReviewNode 从中读取并恢复。
    """
    await task_manager.push_review_response(task_id, body.review_id, body.decision, body.comment)
    return {"status": "ok"}


@router.post("/qa/stream")
async def qa_stream(query: str, workspace_id: str):
    """简单问答 SSE — 直接流式返回答案。

    不走异步任务，直接：
    1. 检索知识图谱
    2. LLM 生成答案（流式）
    3. 通过 SSE 逐 token 返回
    """
    task_id = str(uuid.uuid4())
    return EventSourceResponse(QAStreamer().stream(task_id, query, workspace_id))
```

#### 17.2.3 StreamerRouter

```python
# app/api/streamers/__init__.py — 新增

class StreamerRouter:
    """Streamer 路由器 — 按任务类型分发到对应的 Streamer。"""

    _streamers: dict[str, type[BaseStreamer]] = {
        "generate": GenerationStreamer,
        "qa": QAStreamer,
        "reindex": ReindexStreamer,
        "evaluate": EvaluationStreamer,
    }

    @classmethod
    def get_streamer(cls, task_type: str) -> BaseStreamer:
        streamer_cls = cls._streamers.get(task_type)
        if not streamer_cls:
            raise ValueError(f"未知任务类型: {task_type}")
        return streamer_cls()

    @classmethod
    def register(cls, task_type: str, streamer_cls: type[BaseStreamer]) -> None:
        """扩展：注册自定义 Streamer。"""
        cls._streamers[task_type] = streamer_cls
```

#### 17.2.4 BaseStreamer

```python
# app/api/streamers/base.py — 新增

class BaseStreamer(ABC):
    """Streamer 基类 — 所有流式处理器的通用接口。"""

    @abstractmethod
    async def stream(self, task_id: str, **kwargs) -> AsyncGenerator[SSEEvent, None]:
        """生成 SSE 事件流。子类必须实现。"""
        ...

    async def _emit_progress(self, stage: str, node: str, progress: float) -> SSEEvent:
        """发送进度事件。"""
        return SSEEvent(
            event=SSEEventType.STAGE_PROGRESS,
            data={"stage": stage, "node": node, "progress": progress},
        )

    async def _emit_token(self, text: str, index: int) -> SSEEvent:
        """发送 token 事件。"""
        return SSEEvent(
            event=SSEEventType.TOKEN,
            data={"text": text, "index": index},
        )

    async def _emit_human_review(self, stage: str, question: str, options: list, review_id: str) -> SSEEvent:
        """发送人工介入事件。"""
        return SSEEvent(
            event=SSEEventType.HUMAN_REVIEW,
            data={
                "stage": stage,
                "question": question,
                "options": options,
                "review_id": review_id,
            },
        )

    async def _emit_complete(self, task_id: str, duration_ms: float) -> SSEEvent:
        """发送完成事件。"""
        return SSEEvent(
            event=SSEEventType.COMPLETE,
            data={"task_id": task_id, "duration_ms": duration_ms},
        )

    async def _emit_error(self, code: str, message: str) -> SSEEvent:
        """发送错误事件。"""
        return SSEEvent(
            event=SSEEventType.ERROR,
            data={"code": code, "message": message},
        )
```

#### 17.2.5 GenerationStreamer（场景 A：复杂生成）

```python
# app/api/streamers/generation.py — 新增

class GenerationStreamer(BaseStreamer):
    """复杂生成任务的流式处理器。

    三阶段事件流：
    Phase 1: 进度事件（Analysis + Planning 阶段，无文本流）
           ↓ 需要人工介入时暂停
    Phase 2: 人工审核事件（等待 POST /review 响应）
           ↓ 用户批准后继续
    Phase 3: Token 事件（Generation 阶段，逐 token 流式输出文档）
    """

    def __init__(self):
        self.token_index = 0

    async def stream(self, task_id: str, last_event_id: str = "") -> AsyncGenerator[str, None]:
        """生成 SSE 事件流。"""
        task = await task_manager.get_task(task_id)
        if not task:
            yield self._format_event(self._emit_error("NOT_FOUND", "任务不存在"))
            return

        # 获取该 task 的事件通道
        # TaskManager 在创建 task 时初始化一个 asyncio.Queue
        event_queue = task_manager.get_event_queue(task_id)

        # 如果传了 last_event_id，跳过已发送的事件
        # （断线重连支持）
        skipped = False
        if last_event_id:
            skipped = True

        while True:
            event = await event_queue.get()

            # 断线重连：跳过已发送的事件
            if skipped:
                if event.id == last_event_id:
                    skipped = False
                continue

            yield self._format_event(event)

            if event.event in (SSEEventType.COMPLETE, SSEEventType.ERROR):
                break

    @staticmethod
    def _format_event(event: SSEEvent) -> str:
        """格式化为 SSE 协议。"""
        lines = []
        if event.event:
            lines.append(f"event: {event.event}")
        if event.id:
            lines.append(f"id: {event.id}")
        lines.append(f"data: {json.dumps(event.data, ensure_ascii=False)}")
        lines.append("")
        return "\n".join(lines)


# ── Orchestrator 集成 ──

# 在 OrchestratorState 中新增 event_queue 字段

class OrchestratorState(TypedDict):
    ...
    event_queue: asyncio.Queue     # ← 新增：SSE 事件队列
    review_channel: asyncio.Queue  # ← 新增：人工审核响应通道
    generation_stream: bool        # ← 新增：当前是否处于流式生成阶段


# 在每个 Node 中推送事件

class KnowledgeRetrievalNode:
    async def run(self, state: OrchestratorState) -> OrchestratorState:
        queue = state.get("event_queue")
        if queue:
            await queue.put(SSEEvent(
                event=SSEEventType.STAGE_START,
                data={"stage": "knowledge", "label": "知识检索"},
                id=str(uuid.uuid4()),
            ))
        # ... 执行检索 ...
        if queue:
            await queue.put(SSEEvent(
                event=SSEEventType.STAGE_COMPLETE,
                data={"stage": "knowledge", "duration_ms": elapsed},
            ))
        return state


class HumanReviewNode:
    async def run(self, state: OrchestratorState) -> OrchestratorState:
        queue = state.get("event_queue")
        review_ch = state.get("review_channel")
        review_id = str(uuid.uuid4())

        if queue:
            await queue.put(SSEEvent(
                event=SSEEventType.HUMAN_REVIEW,
                data={
                    "stage": self.stage,
                    "question": f"请审核{self.stage}阶段的结果",
                    "options": ["approved", "needs_changes"],
                    "review_id": review_id,
                },
                id=review_id,
            ))

        # 等待用户通过 API 响应
        # TaskManager.push_review_response() 会把响应放入 review_channel
        response = await review_ch.get()

        if response.get("decision") == "approved":
            return state
        else:
            state["status"] = "paused"
            return state
```

#### 17.2.6 Generation 流式输出集成

需要在 LLM Gateway 和 Generation Layer 之间打通流式通道。

```python
# app/llm_gateway/providers/openai.py — 新增 stream 支持

class OpenAIProvider(BaseProvider):
    async def complete(
        self,
        prompt: str,
        model: str = "",
        stream: bool = False,           # ← 新增
        event_queue: asyncio.Queue | None = None,  # ← 新增
        **kwargs: Any,
    ) -> LLMResponse:
        if stream:
            return await self._complete_stream(prompt, model, event_queue, **kwargs)
        return await self._complete_sync(prompt, model, **kwargs)

    async def _complete_stream(
        self,
        prompt: str,
        model: str,
        event_queue: asyncio.Queue | None,
        **kwargs: Any,
    ) -> LLMResponse:
        """流式调用 LLM，逐 token 推入 event_queue。"""
        model_name = model or self.config.default_model
        response = await self._client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            stream=True,                   # ← OpenAI 流式
            **kwargs,
        )

        full_content = ""
        token_index = 0
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta and event_queue:
                await event_queue.put(SSEEvent(
                    event=SSEEventType.TOKEN,
                    data={"text": delta, "index": token_index},
                    id=f"tok_{token_index}",
                ))
                token_index += 1
            full_content += delta

        # 流式结束
        if event_queue:
            await event_queue.put(SSEEvent(
                event=SSEEventType.TOKEN_DONE,
                data={"total_tokens": token_index},
            ))

        return LLMResponse(
            content=full_content,
            model=model_name,
            input_tokens=0,      # 流式模式下不返回 usage
            output_tokens=0,
        )


# Generation Layer 的 Node 中启用流式

class SectionWriterNode:
    async def run(self, state: GenerationState) -> GenerationState:
        queue = state.get("event_queue")
        # 将 event_queue 透传给 Gateway
        resp = await gateway.complete(
            prompt=prompt,
            task_type="generation",
            stream=True,                    # ← 启用流式
            event_queue=queue,              # ← 传入队列
        )
        ...
```

#### 17.2.7 QAStreamer（场景 B：简单问答）

```python
# app/api/streamers/qa.py — 新增

class QAStreamer(BaseStreamer):
    """简单问答流式处理器。

    不走异步任务，直接在 SSE 中完成：
    1. 检索知识图谱
    2. LLM 生成答案（流式）
    3. 返回引用来源

    适用于：知识查询、文档搜索、简单对话。
    """

    async def stream(
        self,
        task_id: str,
        query: str,
        workspace_id: str,
    ) -> AsyncGenerator[str, None]:
        try:
            # Phase 1: 检索
            yield self._format_event(SSEEvent(
                event=SSEEventType.STAGE_START,
                data={"stage": "retrieval", "label": "知识检索"},
            ))

            pipeline = RetrievalPipeline()
            ctx = await pipeline.retrieve(
                query=query,
                mode="hybrid",
                top_k=5,
                workspace_id=workspace_id,
            )

            yield self._format_event(SSEEvent(
                event=SSEEventType.STAGE_COMPLETE,
                data={"stage": "retrieval", "docs_count": len(ctx.results)},
            ))

            # Phase 2: LLM 生成（流式）
            prompt = f"""根据以下知识回答用户问题。

相关知识：
{self._format_docs(ctx.results)}

用户问题：{query}

请给出简明准确的回答。"""
            token_index = 0
            async for chunk in self._llm_stream(prompt):
                yield self._format_event(SSEEvent(
                    event=SSEEventType.ANSWER_TOKEN,
                    data={"text": chunk, "index": token_index},
                    id=f"ans_{token_index}",
                ))
                token_index += 1

            # Phase 3: 引用来源
            sources = [
                {"title": doc.metadata.get("title", ""), "url": doc.metadata.get("url", ""), "score": doc.score}
                for doc in ctx.results[:3] if doc.score > 0.5
            ]
            yield self._format_event(SSEEvent(
                event=SSEEventType.ANSWER_DONE,
                data={"sources": sources, "total_tokens": token_index},
            ))

        except Exception as e:
            yield self._format_event(self._emit_error("QA_FAILED", str(e)))

    async def _llm_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """流式调用 LLM，逐 token 产出。"""
        response = await openai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta

    @staticmethod
    def _format_docs(docs: list) -> str:
        return "\n\n".join(f"[{i+1}] {d.text[:500]}" for i, d in enumerate(docs[:5]))
```

#### 17.2.8 Human-in-the-Loop 通过 SSE 完成（场景 C）

完整交互流程：

```
客户端                              服务端
  │                                   │
  │  POST /api/v1/interact（complex_generation）               │
  │  ← {"task_id": "task_001"}         │
  │                                   │
  │  GET /api/v1/tasks/task_001/stream │
  │  ← SSE: stage_start (analysis)     │
  │  ← SSE: stage_progress (0.2)      │
  │  ← SSE: stage_progress (0.5)      │
  │  ← SSE: stage_complete             │
  │  ← SSE: human_review              │
  │     {"question":"请确认架构方案",   │
  │      "review_id":"rev_001"}        │
  │  ┌────────────────────────────┐    │
  │  │ 用户看到弹窗，选择"通过"    │    │
  │  └────────────────────────────┘    │
  │  POST /api/v1/tasks/task_001/review│
  │  {"review_id":"rev_001",           │
  │   "decision":"approved"}           │
  │  ← SSE: stage_start (generation)   │
  │  ← SSE: token "## "                │
  │  ← SSE: token "系统架构"           │
  │  ← SSE: token "\n\n"               │
  │  ← SSE: complete                   │
```

#### 17.2.9 断线重连

SSE 原生支持断线重连——客户端传 `Last-Event-ID` 头：

```javascript
// 前端示例
const eventSource = new EventSource(
  `/api/v1/tasks/${taskId}/stream`
);

// 断线后自动重连，浏览器自动带上 Last-Event-ID
eventSource.onerror = () => {
  // 浏览器会自动重连，无需手动处理
};
```

服务端收到 `last_event_id` 参数后，跳过已发送的事件：

```python
# TaskManager 需要保留最近 N 个事件用于重连
class TaskManager:
    def __init__(self):
        self._event_queues: dict[str, asyncio.Queue] = {}
        self._event_history: dict[str, list[SSEEvent]] = {}  # 保留最近 1000 个事件

    async def push_event(self, task_id: str, event: SSEEvent) -> None:
        """推送事件到 task 的队列和历史。"""
        queue = self._event_queues.get(task_id)
        if queue:
            await queue.put(event)
        # 保留历史（最多 1000 条）
        history = self._event_history.setdefault(task_id, [])
        history.append(event)
        if len(history) > 1000:
            history.pop(0)
```

### 17.3 新增文件结构

```
app/api/
├── routes/
│   └── stream.py              # 🆕 SSE 端点（GET /stream + POST /review + POST /qa/stream）
├── streamers/
│   ├── __init__.py
│   ├── base.py                # 🆕 BaseStreamer 基类
│   ├── generation.py          # 🆕 GenerationStreamer（复杂生成三阶段）
│   ├── qa.py                  # 🆕 QAStreamer（简单问答）
│   └── reindex.py             # 🆕 ReindexStreamer（批量任务进度）
├── sse/
│   ├── __init__.py
│   └── events.py              # 🆕 SSEEvent + SSEEventType 定义

app/llm_gateway/providers/
├── openai.py                  # ⬆️ 新增 stream=True 支持
```

### 17.4 验收标准

| 验收项 | 验证方式 |
|--------|---------|
| 复杂生成三阶段事件 | 订阅 SSE → 收到 stage_progress → human_review → token → complete |
| 人工介入可响应 | SSE 收到 human_review → POST /review → SSE 恢复 |
| 简单问答流式 | POST /qa/stream → SSE 收到 answer_token → answer_done |
| Generation 逐 token | 后端用 stream=True 调 LLM → 前端逐字渲染 |
| 断线重连 | 断开后重连带 last_event_id → 不重复发送已收到的 token |
| 进度事件准确 | stage_progress 的 progress 值从 0→1 递增 |

---

## 18. 开发顺序与依赖关系

```
Phase 1（P0 — 核心链路加固）
├── 6. Circuit Breaker          ← 无依赖，可最先做
├── 7. 结构化输出                ← 无依赖，可并行
└── 3. Provider Failover        ← 依赖 Circuit Breaker

Phase 2（P1 — 横向能力补齐）
├── 4. Gateway 护栏拦截器        ← 依赖结构化输出（输出校验需要解析结果）
├── 5. 统一 Task 抽象            ← 无依赖，可独立做
├── 8. Claims 提取              ← 无依赖，可独立做
├── 9. 记忆层增强                ← 依赖结构化输出（摘要需要 LLM）
├── 10. 多租户 Prompt 隔离       ← 无依赖，可独立做
└── 13. 意图驱动的任务路由        ← 依赖 Provider Failover + 记忆层增强（历史上下文）

Phase 3（P0 — 工具系统 + Prompt 管理）
├── 2. Tool Registry            ← 依赖 Provider Failover + 结构化输出
│                                 （Function Calling 需要可靠的 LLM 输出）
├── 11. Prompt 版本管理          ← 无依赖，可独立做
└── 12. Agent 行为回放           ← 依赖工具系统 + TracingMiddleware

Phase 4（集成与测试）
├── 各功能独立测试
├── 集成测试（相互调用场景）
└── 回归测试（确保块 A-E 不受影响）
```

---

## 19. 验收标准汇总

```bash
# 运行所有新增测试
pytest tests/unit/test_circuit_breaker.py -v
pytest tests/unit/test_intent_classifier.py -v
pytest tests/unit/test_tool_registry.py -v
pytest tests/unit/test_failover.py -v
pytest tests/unit/test_guardrails.py -v
pytest tests/unit/test_task_queue.py -v
pytest tests/unit/test_output_parser.py -v
pytest tests/unit/test_claims_extractor.py -v
pytest tests/unit/test_context_compressor.py -v
pytest tests/unit/test_memory_retriever.py -v
pytest tests/unit/test_prompt_manager.py -v
pytest tests/unit/test_prompt_registry.py -v
pytest tests/unit/test_decision_recorder.py -v
pytest tests/unit/test_replay_player.py -v

# 回归测试（确保块 A-E 不受影响）
pytest tests/ -v --tb=short
# 结果: 100% passed, 0 skipped

# 代码质量
ruff check app/ --exit-zero
mypy app/
```

---

## 20. 新增依赖

```yaml
new_deps:
  - jinja2        # Prompt 模板渲染（已在 requirements.txt 中）

# 其余全部使用 Python 标准库 + 已有依赖实现
```

## 21. Contracts 变更

```yaml
contracts/models.py:
  - 新增 Task 模型（TaskStatus / TaskType / Task）
  - 新增 StructuredOutputConfig
  - 新增 TenantPrompt
  - 新增 PromptVersion / ABTestConfig
  - 新增 DecisionRecord / TraceTree
  - 新增 MemoryItem

contracts/interfaces.py:
  - 无需修改（所有新增功能在 contracts 层之下）
```
