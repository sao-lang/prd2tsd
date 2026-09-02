"""观测性模块单元测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from prometheus_client import Counter
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.llm_gateway import LLMGateway
from app.llm_gateway.models import LLMResponse
from app.observability.metrics import (
    HTTP_REQUESTS_TOTAL,
    LLM_CALL_TOTAL,
    LLM_COST_TOTAL,
    LLM_TOKEN_USAGE,
    track_llm_call,
)
from app.observability.tracing import http_tracing_middleware, trace_node


def test_llm_call_metrics_labels() -> None:
    """验证 LLM 调用指标标签设置。"""
    LLM_CALL_TOTAL.labels(model="deepseek-chat", layer="analysis", node="extractor").inc()
    val = LLM_CALL_TOTAL.labels(model="deepseek-chat", layer="analysis", node="extractor")._value.get()
    assert val == 1.0


def test_llm_cost_metrics() -> None:
    """验证成本指标。"""
    LLM_COST_TOTAL.labels(model="gpt-4o-mini").inc(0.5)
    LLM_COST_TOTAL.labels(model="gpt-4o-mini").inc(0.3)
    val = LLM_COST_TOTAL.labels(model="gpt-4o-mini")._value.get()
    assert val == 0.8


def test_llm_token_usage() -> None:
    """验证 Token 消耗指标。"""
    LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="input").inc(150)
    LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="output").inc(50)
    input_val = LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="input")._value.get()
    output_val = LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="output")._value.get()
    assert input_val == 150
    assert output_val == 50


def test_track_llm_call_context_manager() -> None:
    """验证 LLM 调用追踪上下文管理器。"""
    with track_llm_call(model="deepseek-chat", layer="test", node="test_node") as info:
        info["input_tokens"] = 100
        info["output_tokens"] = 50

    # 验证指标已记录
    call_val = LLM_CALL_TOTAL.labels(
        model="deepseek-chat",
        layer="test",
        node="test_node",
    )._value.get()
    assert call_val >= 1.0


def test_llm_call_total_is_counter() -> None:
    """验证 LLM_CALL_TOTAL 已从 Gauge 改为 Counter 类型。"""
    assert isinstance(LLM_CALL_TOTAL, Counter)


def test_trace_node_detects_sync_async() -> None:
    """验证 trace_node 自动识别同步/异步节点并正确包装。"""

    async def async_fn(state: dict) -> dict:
        """异步节点函数。"""
        return state

    def sync_fn(state: dict) -> dict:
        """同步节点函数。"""
        return state

    wrapped_async = trace_node("async_node")(async_fn)
    wrapped_sync = trace_node("sync_node")(sync_fn)

    assert asyncio.iscoroutinefunction(wrapped_async)
    assert not asyncio.iscoroutinefunction(wrapped_sync)
    # 包装不改变函数行为
    assert asyncio.run(wrapped_async({"a": 1})) == {"a": 1}
    assert wrapped_sync({"a": 1}) == {"a": 1}


async def test_gateway_complete_records_llm_metrics() -> None:
    """验证 Gateway.complete() 真实调用后 LLM 指标被记录。"""
    gw = LLMGateway()
    gw.guardrails = MagicMock()
    gw.guardrails.check_input = AsyncMock(return_value=[])
    gw.guardrails.check_output = AsyncMock(return_value=[])
    gw.rate_limiter = MagicMock()
    gw.rate_limiter.reserve = AsyncMock(
        return_value={"allowed": True, "retry_after": 0, "reservation_id": "reservation"},
    )
    gw.rate_limiter.reconcile = AsyncMock()
    gw.budget_controller = MagicMock()
    gw.budget_controller.check = AsyncMock(return_value={})
    gw.budget_controller.record_usage = AsyncMock()
    gw.cache = MagicMock()
    gw.cache.make_key = MagicMock(return_value="test-key")
    gw.cache.get = MagicMock(return_value=None)
    gw.cache.set = MagicMock()
    gw.cost_tracker = MagicMock()
    # 固定路由模型名，保证指标标签可断言
    model_cfg = MagicMock()
    model_cfg.provider = "deepseek"
    gw.config_manager.resolve_model = MagicMock(return_value=(model_cfg, "deepseek-chat"))
    gw._failover_call = AsyncMock(
        return_value=(
            LLMResponse(
                content="你好",
                model="deepseek-chat",
                cached=False,
                cost=0.001,
                input_tokens=10,
                output_tokens=20,
            ),
            "deepseek-chat",
        )
    )

    resp = await gw.complete(
        prompt="测试",
        task_type="chat",
        layer="test",
        node="test_node",
    )

    assert resp.content == "你好"
    # 调用次数 +1
    call_val = LLM_CALL_TOTAL.labels(
        model="deepseek-chat",
        layer="test",
        node="test_node",
    )._value.get()
    assert call_val >= 1.0
    # token 指标
    input_val = LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="input")._value.get()
    assert input_val >= 10
    output_val = LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="output")._value.get()
    assert output_val >= 20
    # 成本指标
    cost_val = LLM_COST_TOTAL.labels(model="deepseek-chat")._value.get()
    assert cost_val >= 0.001


async def test_http_tracing_middleware_creates_root_span() -> None:
    """验证 http_tracing_middleware 生成 HTTP 根 Span 并记录 HTTP 指标。"""
    scope: dict = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/health",
        "raw_path": b"/api/v1/health",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
        "auth.user_id": "user-1",
    }
    request = Request(scope)

    async def call_next(req: Request) -> JSONResponse:
        """模拟下一个处理函数。"""
        return JSONResponse({"ok": True}, status_code=200)

    with patch("app.observability.tracing.tracer") as mock_tracer:
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        response = await http_tracing_middleware(request, call_next)

    assert response.status_code == 200
    mock_tracer.start_as_current_span.assert_called_once()
    # HTTP 指标已记录
    req_val = HTTP_REQUESTS_TOTAL.labels(
        method="GET",
        path="/api/v1/health",
        status="200",
    )._value.get()
    assert req_val >= 1.0
