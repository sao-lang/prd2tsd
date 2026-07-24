"""集成生态 API 路由 — Webhook 注册/测试。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.schemas.integration import WebhookRegisterRequest, WebhookTestResponse
from app.auth.deps import get_current_user
from app.auth.middleware import _SCOPE_WS_ID as _SCOPE_WORKSPACE_ID
from app.core.logger import get_logger
from app.integrations.webhook import WebhookSender, integration_hub

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
logger = get_logger("prd2tsd.integrations")


def _get_workspace_id(request: Request) -> str:
    ws_id = request.scope.get(_SCOPE_WORKSPACE_ID)
    if not ws_id:
        raise HTTPException(status_code=400, detail="缺少工作空间上下文")
    return ws_id


@router.post("/webhooks", status_code=201)
async def register_webhook(
    request: Request,
    req: WebhookRegisterRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """注册 Webhook。

    Args:
        request: FastAPI 请求。
        req: 注册请求。
        user_id: 当前用户 ID。

    Returns:
        注册结果。
    """
    ws_id = _get_workspace_id(request)
    integration_hub.register_webhook(ws_id, req.url, req.event)
    return {"status": "registered", "workspace_id": ws_id, "event": req.event, "url": req.url}


@router.delete("/webhooks", status_code=200)
async def unregister_webhook(
    request: Request,
    event: str = "task.completed",
    user_id: str = Depends(get_current_user),
) -> dict:
    """注销 Webhook。

    Args:
        request: FastAPI 请求。
        event: 事件类型。
        user_id: 当前用户 ID。

    Returns:
        注销结果。
    """
    ws_id = _get_workspace_id(request)
    success = integration_hub.unregister_webhook(ws_id, event)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook 未注册")
    return {"status": "unregistered", "workspace_id": ws_id, "event": event}


@router.post("/webhooks/test", response_model=WebhookTestResponse)
async def test_webhook(
    request: Request,
    req: WebhookRegisterRequest,
    user_id: str = Depends(get_current_user),
) -> WebhookTestResponse:
    """测试 Webhook 连通性。

    Args:
        request: FastAPI 请求。
        req: Webhook 配置。
        user_id: 当前用户 ID。

    Returns:
        测试结果。
    """
    sender = WebhookSender(secret=req.secret or "")
    result = await sender.send_task_completed(
        url=req.url,
        task_id="test-task",
        workspace_id=_get_workspace_id(request),
        summary="Webhook 连通性测试",
    )
    return WebhookTestResponse(**result)


@router.get("/webhooks", response_model=list[dict])
async def list_webhooks(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> list[dict]:
    """列出已注册的 Webhook。

    Args:
        request: FastAPI 请求。
        user_id: 当前用户 ID。

    Returns:
        Webhook 列表。
    """
    ws_id = _get_workspace_id(request)
    return integration_hub.list_webhooks(ws_id)
