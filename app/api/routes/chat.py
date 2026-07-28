"""统一 Chat 入口 — 通过 LangGraph 主编排图自动分流。

Phase 2 重构：chat / knowledge_qa / complex_generation / clarification
全部通过 LangGraph StateGraph 的 classify → route_by_intent 自动路由，
不再在路由处理器中手动 if/elif 分支。

Block F §13 — IntentClassifier 集成。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import get_orchestrator
from app.core.logger import get_logger
from app.llm_gateway import gateway
from app.orchestrator.intent_classifier import IntentClassifier, IntentType
from app.orchestrator.state import make_initial_state

logger = get_logger("prd2tsd.chat_route")
router = APIRouter(prefix="/api/v1")


class ChatRequest(BaseModel):
    """统一聊天请求。"""

    message: str
    session_id: str = ""
    workspace_id: str = ""


class ChatResponse(BaseModel):
    """聊天响应。"""

    intent: str
    confidence: float
    message: str
    session_id: str = ""


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """统一入口 — 通过 LangGraph 图自动分流。

    使用主编排 StateGraph 的 classify 节点做意图分类，
    route_by_intent 条件边自动路由到对应处理节点：
    - chat → ChatNode（LLM 直接回答）
    - knowledge_qa → KnowledgeQANode（知识检索 + LLM 回答）
    - complex_generation → 全链路异步生成
    - clarification → ClarifyNode（提示补充信息）

    Args:
        req: ChatRequest 包含消息和上下文。

    Returns:
        ChatResponse 包含分类结果和处理消息。
    """
    # 1. 意图分类（快速规则匹配，无需 LLM 可秒出结果）
    classifier = IntentClassifier(llm_gateway=gateway)
    intent_result = await classifier.classify(user_input=req.message)
    intent = intent_result.intent

    # 2. complex_generation → 异步任务（不走同步 ainvoke）
    if intent == IntentType.COMPLEX_GENERATION:
        from app.task_manager import task_manager

        task_id = await task_manager.create_task(
            prd_raw=req.message,
            workspace_id=req.workspace_id,
        )
        return ChatResponse(
            intent="complex_generation",
            confidence=intent_result.confidence,
            message=f"已创建生成任务: {task_id}",
            session_id=req.session_id,
        )

    # 3. chat / knowledge_qa / clarification → 走 LangGraph 图同步执行
    orchestrator = get_orchestrator()
    task_id = str(uuid.uuid4())
    initial_state = make_initial_state(
        task_id=task_id,
        prd_raw=req.message,
        workspace_id=req.workspace_id,
    )
    config = {"configurable": {"thread_id": task_id}}

    try:
        final_state = await orchestrator.ainvoke(initial_state, config)
        chat_response = final_state.get("chat_response", "") if isinstance(final_state, dict) else ""
        status = final_state.get("status", "complete") if isinstance(final_state, dict) else "complete"

        return ChatResponse(
            intent=intent,
            confidence=intent_result.confidence,
            message=chat_response or f"处理完成 (status={status})",
            session_id=req.session_id,
        )
    except Exception as exc:
        logger.exception("LangGraph 图执行失败: %s", exc)
        # 降级：直接 LLM 回答
        resp = await gateway.complete(
            prompt=req.message,
            task_type="chat",
            temperature=0.7,
            max_tokens=1024,
        )
        return ChatResponse(
            intent="chat",
            confidence=0.5,
            message=resp.content,
            session_id=req.session_id,
        )
