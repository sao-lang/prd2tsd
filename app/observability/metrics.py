"""Prometheus 指标定义 — LLM 调用 + 业务流程指标。"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response

from app.core.logger import get_logger

logger = get_logger("prd2tsd.metrics")

# ── LLM 调用指标 ──

LLM_CALL_TOTAL: Gauge = Gauge(
    "llm_calls_total",
    "LLM 调用总数",
    ["model", "layer", "node"],
)

LLM_COST_TOTAL: Counter = Counter(
    "llm_cost_total_usd",
    "LLM 累计成本（美元）",
    ["model"],
)

LLM_LATENCY: Histogram = Histogram(
    "llm_latency_seconds",
    "LLM 响应延迟",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

LLM_TOKEN_USAGE: Counter = Counter(
    "llm_tokens_total",
    "Token 消耗",
    ["model", "type"],
)

# ── 业务流程指标 ──

TASKS_TOTAL: Counter = Counter(
    "tasks_total",
    "任务总数",
    ["status"],
)

TASKS_DURATION: Histogram = Histogram(
    "tasks_duration_seconds",
    "任务耗时",
    buckets=[10, 30, 60, 120, 300, 600, 1800],
)

# ── 业务指标 ──

SESSIONS_TOTAL: Counter = Counter(
    "sessions_total",
    "会话总数",
    ["workspace_id"],
)

DOCUMENTS_TOTAL: Gauge = Gauge(
    "documents_total",
    "文档总数",
    ["workspace_id", "file_type"],
)

DOCUMENTS_STORAGE_BYTES: Gauge = Gauge(
    "documents_storage_bytes",
    "文档存储总量（字节）",
    ["workspace_id"],
)


@contextmanager
def track_llm_call(
    model: str,
    layer: str = "",
    node: str = "",
) -> Generator[dict[str, Any], None, None]:
    """追踪一次 LLM 调用（上下文管理器）。

    自动记录调用次数、延迟分布。

    Args:
        model: 模型名。
        layer: 所属层。
        node: 所属节点。

    Yields:
        用于记录 token 数的字典。调用方在块内设置 input_tokens / output_tokens。
    """
    labels = [model, layer, node]
    LLM_CALL_TOTAL.labels(*labels).inc()

    start = time.monotonic()
    token_info: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}

    try:
        yield token_info
    finally:
        elapsed = time.monotonic() - start
        LLM_LATENCY.labels(model).observe(elapsed)

        input_tokens = token_info.get("input_tokens", 0)
        output_tokens = token_info.get("output_tokens", 0)
        if input_tokens:
            LLM_TOKEN_USAGE.labels(model, "input").inc(input_tokens)
        if output_tokens:
            LLM_TOKEN_USAGE.labels(model, "output").inc(output_tokens)


async def metrics_app(request: Request) -> Response:
    """Prometheus 指标暴露端点。

    Args:
        request: FastAPI 请求对象。

    Returns:
        包含所有 Prometheus 指标的响应。
    """
    data = generate_latest()
    return Response(
        content=data,
        media_type=CONTENT_TYPE_LATEST,
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
