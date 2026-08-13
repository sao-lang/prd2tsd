"""OpenTelemetry 分布式追踪 — 全链路 Span 追踪。"""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logger import get_logger
from app.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL

logger = get_logger("prd2tsd.tracing")


def _init_tracer() -> trace.Tracer:
    """初始化 OpenTelemetry Tracer。

    配置 OTLP Exporter 连接到 Jaeger。

    Returns:
        配置好的 Tracer 实例。
    """
    resource = Resource.create({
        "service.name": settings.OTEL_SERVICE_NAME,
        "service.version": "0.1.0",
    })
    provider = TracerProvider(resource=resource)

    otlp_endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if otlp_endpoint:
        try:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
            logger.info("OTLP Span Exporter 已配置: %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("OTLP Exporter 初始化失败: %s", exc)
    else:
        logger.info("OTLP 未配置，使用内存 SpanProcessor")

    trace.set_tracer_provider(provider)
    return trace.get_tracer("prd2tsd")


# 全局 Tracer 实例
tracer = _init_tracer()


class TracingMiddleware:
    """LangGraph Node 追踪中间件。

    自动为每个节点函数创建 Span，记录 task_id / workspace_id / layer / node 等属性。
    """

    def wrap_node(
        self,
        node_fn: Callable[..., Any],
        node_name: str,
    ) -> Callable[..., Any]:
        """包装节点函数，添加追踪。

        Args:
            node_fn: 原始节点函数。
            node_name: 节点名称（如 "requirement_extractor"）。

        Returns:
            包装后的节点函数。
        """

        @functools.wraps(node_fn)
        def traced_node(*args: Any, **kwargs: Any) -> Any:
            """被追踪的节点函数。"""
            state = args[0] if args else kwargs.get("state", {})

            attributes: dict[str, Any] = {
                "node": node_name,
            }
            if isinstance(state, dict):
                attributes["task_id"] = state.get("task_id", "")
                attributes["workspace_id"] = state.get("workspace_id", "")
                attributes["layer"] = state.get("current_layer", "")
                attributes["iteration"] = state.get("iteration_count", 0)

            with tracer.start_as_current_span(
                f"node.{node_name}",
                attributes=attributes,
                kind=trace.SpanKind.INTERNAL,
            ) as span:
                try:
                    start = time.monotonic()
                    result = node_fn(*args, **kwargs)
                    elapsed = time.monotonic() - start
                    span.set_attribute("duration_ms", round(elapsed * 1000, 2))
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(trace.StatusCode.ERROR, str(exc))
                    raise

        return traced_node

    def wrap_async_node(
        self,
        node_fn: Callable[..., Any],
        node_name: str,
    ) -> Callable[..., Any]:
        """包装异步节点函数，添加追踪。

        Args:
            node_fn: 原始异步节点函数。
            node_name: 节点名称。

        Returns:
            包装后的异步节点函数。
        """

        @functools.wraps(node_fn)
        async def traced_node(*args: Any, **kwargs: Any) -> Any:
            """被追踪的异步节点函数。"""
            state = args[0] if args else kwargs.get("state", {})

            attributes: dict[str, Any] = {
                "node": node_name,
            }
            if isinstance(state, dict):
                attributes["task_id"] = state.get("task_id", "")
                attributes["workspace_id"] = state.get("workspace_id", "")
                attributes["layer"] = state.get("current_layer", "")
                attributes["iteration"] = state.get("iteration_count", 0)

            with tracer.start_as_current_span(
                f"node.{node_name}",
                attributes=attributes,
                kind=trace.SpanKind.INTERNAL,
            ) as span:
                try:
                    start = time.monotonic()
                    result = await node_fn(*args, **kwargs)
                    elapsed = time.monotonic() - start
                    span.set_attribute("duration_ms", round(elapsed * 1000, 2))
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(trace.StatusCode.ERROR, str(exc))
                    raise

        return traced_node


# 全局 TracingMiddleware 实例
tracing_middleware = TracingMiddleware()


def trace_node(node_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """统一节点追踪包装器。

    根据节点函数是否为协程自动选择 wrap_node（同步）或 wrap_async_node（异步），
    避免人工判断节点类型导致漏包/错包。

    Args:
        node_name: 节点名称（如 "requirement_extractor"）。

    Returns:
        装饰器，接受原始节点函数并返回包装后的节点函数。
    """

    def decorator(node_fn: Callable[..., Any]) -> Callable[..., Any]:
        """装饰器：包装节点函数。

        Args:
            node_fn: 原始节点函数。

        Returns:
            包装后的节点函数。
        """
        if inspect.iscoroutinefunction(node_fn):
            return tracing_middleware.wrap_async_node(node_fn, node_name)
        return tracing_middleware.wrap_node(node_fn, node_name)

    return decorator


async def http_tracing_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """HTTP 请求追踪中间件（FastAPI @app.middleware("http") 形态）。

    为每个 HTTP 请求创建根 Span，并记录 Prometheus HTTP 指标
    （http_requests_total / http_request_duration_seconds）。

    Args:
        request: FastAPI 请求对象。
        call_next: 下一个处理函数。

    Returns:
        Response。
    """
    method = request.method
    path = request.url.path
    user_id = str(request.scope.get("auth.user_id", ""))

    attributes: dict[str, Any] = {
        "http.method": method,
        "http.path": path,
        "http.user_id": user_id,
    }
    start = time.monotonic()
    status = "500"
    with tracer.start_as_current_span(
        f"http.{method} {path}",
        attributes=attributes,
        kind=trace.SpanKind.SERVER,
    ) as span:
        try:
            response = await call_next(request)
            status = str(response.status_code)
            # AuthMiddleware 在内层执行，此时 scope 中才有完整用户上下文
            resolved_user_id = str(request.scope.get("auth.user_id", ""))
            span.set_attribute("http.user_id", resolved_user_id)
            span.set_attribute("http.status_code", response.status_code)
            span.set_status(trace.StatusCode.OK)
            return response
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            raise
        finally:
            elapsed = time.monotonic() - start
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
            HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(elapsed)
