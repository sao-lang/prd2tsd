"""跨 Layer 数据模型 — 所有模型调用方统一使用。

Block F 新增：
- Task / TaskStatus / TaskType — 统一任务模型
- StructuredOutputConfig — 结构化输出配置
- TenantPrompt — 租户级 Prompt 模板
- PromptVersion / ABTestConfig — Prompt 版本管理
- DecisionRecord / TraceTree — Agent 行为回放
- MemoryItem — 记忆检索条目
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ModelType(StrEnum):
    """模型类型枚举 — 涵盖所有模型调用场景。"""

    LLM = "llm"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    JUDGE = "judge"
    VISION = "vision"
    AUDIO = "audio"
    IMAGE = "image"


class ProviderType(StrEnum):
    """支持的模型供应商。"""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    AZURE_OPENAI = "azure_openai"
    COHERE = "cohere"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


class ModelConfig(BaseModel):
    """单个模型的完整配置 — 所有模型调用方统一使用此结构。"""

    provider: ProviderType = ProviderType.OPENAI
    api_key: str = ""
    base_url: str = ""
    default_model: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    timeout: int = 60
    max_retries: int = 3

    def masked_api_key(self) -> str:
        """返回掩码后的 API Key，用于日志和 API 响应。

        Returns:
            掩码后的 Key，例如 "sk-a***f456"。
        """
        if not self.api_key or len(self.api_key) < 8:
            return "****"
        return self.api_key[:4] + "****" + self.api_key[-4:]


class ModelEndpointConfig(BaseModel):
    """某模型类型的完整配置（支持多供应商、多模型）。"""

    type: ModelType
    providers: dict[str, ModelConfig] = Field(default_factory=dict)
    default_provider: str = ""
    default_model: str = ""


class RoutingRule(BaseModel):
    """模型路由规则 — task_type → 模型映射。"""

    type: ModelType = ModelType.LLM
    provider: str = ""
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class FullModelConfig(BaseModel):
    """完整模型配置（所有类型 + 路由规则）。"""

    endpoints: dict[ModelType, ModelEndpointConfig] = Field(default_factory=dict)
    routing_rules: dict[str, RoutingRule] = Field(default_factory=dict)


class ModelConfigUpdate(BaseModel):
    """模型配置更新请求体（API 动态注入用）。"""

    type: ModelType
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    config: dict[str, Any] | None = None
    timeout: int | None = None
    max_retries: int | None = None


class RoutingRuleUpdate(BaseModel):
    """路由规则更新请求体（API 动态注入用）。"""

    task_type: str
    type: ModelType | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    config: dict[str, Any] | None = None


# ════════════════════════════════════════════
# Block F — 统一 Task 模型（§5）
# ════════════════════════════════════════════


class TaskStatus(StrEnum):
    """任务状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    """任务类型枚举。"""

    GENERATE = "generate"  # PRD→TSD 生成
    REINDEX = "reindex"  # 文档重索引
    REGENERATE = "regenerate"  # 方案重新生成
    EVALUATE = "evaluate"  # 方案评测
    WEB_SYNC = "web_sync"  # Web 资源同步


class Task(BaseModel):
    """统一任务模型。"""

    id: str
    type: TaskType = TaskType.GENERATE
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0  # 0=最高, 越大越优先
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


# ════════════════════════════════════════════
# Block F — 结构化输出配置（§7）
# ════════════════════════════════════════════


class StructuredOutputConfig(BaseModel):
    """结构化输出配置。"""

    enabled: bool = False
    json_schema: dict[str, Any] | None = None  # JSON Schema
    strict: bool = True  # 严格模式


# ════════════════════════════════════════════
# Block F — 多租户 Prompt 隔离（§10）
# ════════════════════════════════════════════


class TenantPrompt(BaseModel):
    """租户级 Prompt 模板。"""

    id: str = ""
    organization_id: str
    agent_name: str  # analysis / planning / generation / evaluation
    node_name: str  # requirement_extractor / pattern_recommend ...
    template: str  # Jinja2 模板
    variables: dict[str, str] = Field(default_factory=dict)  # 默认变量值
    version: int = 1
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ════════════════════════════════════════════
# Block F — Prompt 版本管理（§11）
# ════════════════════════════════════════════


class PromptVersion(BaseModel):
    """Prompt 版本。"""

    id: str = ""
    name: str  # "analysis.requirement"
    version: int  # 自增版本号
    content: str  # Prompt 文本
    hash: str = ""  # SHA-256 内容哈希
    author: str = ""
    changelog: str = ""
    is_active: bool = False
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ABTestConfig(BaseModel):
    """A/B 测试配置。"""

    prompt_name: str
    version_a: int
    version_b: int
    traffic_split: float = 0.5  # A 版本流量占比
    metric: str = "eval_score"  # 对比指标
    is_active: bool = False


# ════════════════════════════════════════════
# Block F — Agent 行为回放（§12）
# ════════════════════════════════════════════


class DecisionRecord(BaseModel):
    """单次决策记录。"""

    id: str = ""
    task_id: str
    trace_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_name: str = ""  # analysis / planning / generation / evaluation
    node_name: str = ""  # requirement_extractor / pattern_recommend ...
    iteration_count: int = 0
    input_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_prompt: str = ""
    input_tools: list[dict[str, Any]] = Field(default_factory=list)
    llm_response: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    output_state_diff: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    tokens_consumed: int = 0
    decision_summary: str = ""


class TraceTree(BaseModel):
    """全链路追踪树 — 一个 task 的完整决策链。"""

    task_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    total_duration_ms: float = 0.0
    nodes: list[DecisionRecord] = Field(default_factory=list)
    edges: list[tuple[str, str, str]] = Field(default_factory=list)


# ════════════════════════════════════════════
# Block F — 记忆检索条目（§9）
# ════════════════════════════════════════════


class MemoryItem(BaseModel):
    """记忆条目。"""

    id: str = ""
    content: str
    role: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str = ""
    recency_score: float = 0.0
    relevance_score: float = 0.0
    importance_score: float = 0.0
    composite_score: float = 0.0
