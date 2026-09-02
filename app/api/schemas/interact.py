"""统一交互入口 API 请求/响应体（Block E B1）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InteractRequest(BaseModel):
    """统一交互请求体。

    对话 / 提问 / 文档分析 / 复杂生成 合并为单一入口，服务端按意图识别分流。
    """

    message: str = Field(..., min_length=1, description="用户输入（对话/提问/PRD 内容/分析指令）")
    session_id: str = Field(default="", description="关联会话 ID（可选）")
    workspace_id: str = Field(default="", description="工作空间 ID（可选）")
    stream: bool = Field(default=False, description="true → SSE 流式返回")
    doc_id: str = Field(default="", description="对已上传文档提问/分析")
    url: str = Field(default="", description="对 URL 分析/生成")
    generate: bool = Field(default=False, description="URL 分析后一键生成 TSD（转 complex_generation）")
    prd_type: str = Field(default="md", pattern="^(md|pdf|docx|txt)$", description="生成意图：PRD 类型")
    provider: str = Field(default="", max_length=64, description="单次请求覆盖的模型 Provider（可选）")
    model: str = Field(default="", max_length=128, description="单次请求覆盖的模型名称（可选）")
    estimated_tokens: int | None = Field(default=None, ge=0, description="调用前用于 TPM 预留的预计 Token")
    max_tokens: int | None = Field(default=None, ge=1, le=131072, description="模型最大输出 Token")
    timeout: float | None = Field(default=None, gt=0, le=600, description="单次 Provider 尝试超时秒数")


class InteractResponse(BaseModel):
    """统一交互响应体（同步模式）。"""

    intent: str = Field(..., description="识别到的意图")
    confidence: float = Field(default=0.0, description="置信度 0.0~1.0")
    message: str = Field(..., description="回答文本")
    task_id: str = Field(default="", description="complex_generation 同步模式返回任务 ID")
    session_id: str = Field(default="", description="关联会话 ID")
