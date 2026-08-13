"""FastAPI 应用入口。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api.routes import auth as auth_routes
from app.api.routes import batch as batch_routes
from app.api.routes import documents as documents_routes
from app.api.routes import evaluate as evaluate_routes
from app.api.routes import generate as generate_routes
from app.api.routes import integrations as integrations_routes
from app.api.routes import interact as interact_routes
from app.api.routes import knowledge as knowledge_routes
from app.api.routes import model_config as model_config_routes
from app.api.routes import review as review_routes
from app.api.routes import sessions as sessions_routes
from app.api.routes import stream_generate as stream_generate_routes
from app.api.routes import web_indexing as web_indexing_routes
from app.api.routes import workspace as workspace_routes
from app.api.routes import workspace_members as workspace_members_routes
from app.api.schemas.response import HealthResponse
from app.auth.middleware import AuthMiddleware, WorkspaceContextMiddleware
from app.core.config import settings
from app.core.connections import connection_manager, init_connections
from app.core.exceptions import Prd2TsdError
from app.core.logger import get_logger, setup_logger
from app.llm_gateway import config_manager
from app.observability.metrics import metrics_app
from app.observability.tracing import http_tracing_middleware

logger = get_logger("prd2tsd")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理。

    Args:
        app: FastAPI 应用实例。
    """
    # 启动
    setup_logger()
    logger.info("正在启动 %s...", settings.APP_NAME)

    # 初始化连接
    init_connections()
    await connection_manager.startup()

    # 初始化 LLM Gateway
    logger.info("LLM Gateway 就绪")

    # Block E: 初始化 EventBus 并注入 TaskManager
    from app.streaming import event_bus
    from app.task_manager import task_manager

    task_manager.set_event_bus(event_bus)
    logger.info("EventBus 已就绪，已注入 TaskManager")

    # Phase 1: 初始化 PostgreSQL Checkpointer（断点持久化恢复）
    try:
        from app.api.deps import set_checkpointer
        from app.orchestrator.main_graph import create_postgres_checkpointer

        checkpointer = await create_postgres_checkpointer()
        set_checkpointer(checkpointer)
        logger.info("PostgreSQL Checkpointer 已初始化（断点恢复已启用）")
    except Exception as exc:
        logger.warning("PostgreSQL Checkpointer 初始化失败，降级使用 MemorySaver: %s", exc)
        from app.api.deps import set_checkpointer
        from app.orchestrator.main_graph import create_memory_checkpointer

        checkpointer = await create_memory_checkpointer()
        set_checkpointer(checkpointer)
        logger.info("MemorySaver Checkpointer 已初始化（开发模式）")

    # Block F: Agent 工具已废弃 — ToolRegistry 零调用，待 LangChain @tool + ToolNode 替代
    # 工具注册代码已注释，不再注册零调用工具
    # 如需启用，请在 LangChain ToolNode 中重新注册
    logger.info("Agent 工具已废弃，待迁移至 LangChain ToolNode")

    # Block F: 初始化观测性
    from app.observability import tracer  # noqa: F401
    logger.info("OpenTelemetry 追踪已初始化: %s", settings.OTEL_SERVICE_NAME)

    logger.info("%s 启动完成", settings.APP_NAME)
    yield

    # 关闭
    logger.info("正在关闭 %s...", settings.APP_NAME)
    await connection_manager.shutdown()
    logger.info("%s 已关闭", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description="PRD to Technical Specification Document Agent System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — 不允许 allow_credentials=True 与 allow_origins=["*"] 同时使用
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if hasattr(settings, "CORS_ORIGINS") else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth 中间件
app.add_middleware(AuthMiddleware)
app.add_middleware(WorkspaceContextMiddleware)

# HTTP 追踪中间件 — 每个 /api/v1/* 请求成为 trace 根 span
app.middleware("http")(http_tracing_middleware)


# 全局异常处理
@app.exception_handler(Prd2TsdError)
async def prd2tsd_error_handler(request: Request, exc: Prd2TsdError) -> JSONResponse:
    """处理 Prd2TsdError 异常。

    Args:
        request: 请求对象。
        exc: 异常实例。

    Returns:
        JSON 错误响应。
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


# ── 健康检查 ──


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查接口。

    检查所有基础设施服务的连接状态和模型配置就绪情况。

    Returns:
        健康检查响应。
    """
    conn_health = await connection_manager.health_check()

    # 检查模型配置
    model_config_status = {
        "llm": config_manager.get_config("llm", "deepseek").api_key != "",
        "embedding": config_manager.get_config("embedding", "openai").api_key != "",
        "judge": config_manager.get_config("judge", "openai").api_key != "",
    }

    overall_status = "ok"
    for _, health in conn_health.items():
        if health.get("enabled") and not health.get("connected"):
            overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        connections=conn_health,
        gateway="ready",
        model_config=model_config_status,
    )


# ── Prometheus 指标端点 ──


@app.get("/api/v1/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    """Prometheus 指标暴露端点。

    Args:
        request: 请求对象。

    Returns:
        Prometheus 格式的指标数据。
    """
    return await metrics_app(request)


# ── 注册路由 ──

app.include_router(auth_routes.router)
app.include_router(workspace_routes.router)
app.include_router(workspace_members_routes.router)
app.include_router(model_config_routes.router)
app.include_router(knowledge_routes.router)
app.include_router(generate_routes.router)
app.include_router(review_routes.router)
app.include_router(evaluate_routes.router)
app.include_router(sessions_routes.router)
app.include_router(documents_routes.router)
app.include_router(web_indexing_routes.router)
app.include_router(integrations_routes.router)
app.include_router(batch_routes.router)
app.include_router(interact_routes.router)  # Block E: 统一交互入口（意图分流）
app.include_router(stream_generate_routes.router)  # Block E: SSE 流式任务事件


@app.get("/")
async def root() -> dict:
    """根路径。

    Returns:
        应用基本信息。
    """
    return {
        "app": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
    }
