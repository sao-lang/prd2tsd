"""RAG 评测数据模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class RagSample(BaseModel):
    """RAG 评测黄金样本。

    Attributes:
        id: 样本唯一 ID。
        query: 用户查询。
        reference_answer: 黄金答案。
        reference_contexts: 期望检索命中的关键上下文。
        source_file: 数据来源文件。
        expected_mode: 期望检索模式（local/global/hybrid）。
    """

    id: str
    query: str
    reference_answer: str = ""
    reference_contexts: list[str] = Field(default_factory=list)
    source_file: str = ""
    expected_mode: str = "hybrid"


class RagQueryScore(BaseModel):
    """单条查询的 RAG 评测得分。

    Attributes:
        sample_id: 样本 ID。
        context_precision: 上下文精确率（deepeval L1）。
        context_recall: 上下文召回率（deepeval L1）。
        faithfulness: 忠实度（deepeval L2）。
        answer_relevancy: 回答相关性（deepeval L2）。
        retrieved_count: 检索结果数。
        reflection_rounds: 反思轮数（当前 pipeline 未暴露，默认 0）。
        total_tokens: 检索消耗 token 数。
    """

    sample_id: str
    context_precision: float = 0.0
    context_recall: float = 0.0
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    retrieved_count: int = 0
    reflection_rounds: int = 0
    total_tokens: int = 0


class RagEvalSummary(BaseModel):
    """RAG 评测汇总。"""

    samples: int = 0
    avg_context_precision: float = 0.0
    avg_context_recall: float = 0.0
    avg_faithfulness: float = 0.0
    avg_answer_relevancy: float = 0.0


class RagEvalReport(BaseModel):
    """RAG 评测报告。

    Attributes:
        dataset_version: 数据集版本。
        config: 评测配置（top_k/mode/reflection 等）。
        summary: 汇总得分。
        queries: 按查询明细。
        timestamp: 报告生成时间。
    """

    dataset_version: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    summary: RagEvalSummary = Field(default_factory=RagEvalSummary)
    queries: list[RagQueryScore] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
