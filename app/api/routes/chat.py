"""统一 Chat 入口 — 自动分流：对话 / 知识查询 / 复杂生成。

Block F §13 — IntentClassifier 集成。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logger import get_logger
from app.llm_gateway import gateway
from app.orchestrator.intent_classifier import IntentClassifier, IntentType

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
    """统一入口 — 自动分流到对应处理器。

    服务端自动判断意图，路由到正确路径：
    - chat → 直接 LLM 回答
    - knowledge_qa → 知识检索 + LLM 回答
    - complex_generation → 全链路异步生成

    Args:
        req: ChatRequest 包含消息和上下文。

    Returns:
        ChatResponse 包含分类结果和处理消息。
    """
    # 1. 意图分类
    classifier = IntentClassifier(llm_gateway=gateway)
    intent_result = await classifier.classify(
        user_input=req.message,
    )

    intent = intent_result.intent

    # 2. 按意图路由
    if intent == IntentType.CHAT:
        resp = await gateway.complete(
            prompt=req.message,
            task_type="chat",
            temperature=0.7,
            max_tokens=1024,
        )
        return ChatResponse(
            intent="chat",
            confidence=intent_result.confidence,
            message=resp.content,
            session_id=req.session_id,
        )

    elif intent == IntentType.KNOWLEDGE_QA:
        # 知识检索 + LLM 回答
        try:
            from app.knowledge_layer.pipeline import RetrievalPipeline

            pipeline = RetrievalPipeline()
            ctx = await pipeline.retrieve(
                query=req.message,
                mode="hybrid",
                top_k=5,
                workspace_id=req.workspace_id,
            )
            docs_text = "\n\n".join(
                f"[{i+1}] {d.text[:500]}" for i, d in enumerate(ctx.results[:5])
            )
            prompt = f"""根据以下知识回答用户问题。

相关知识：
{docs_text}

用户问题：{req.message}

请给出简明准确的回答。"""
        except Exception as e:
            logger.warning("知识检索失败，降级到纯 LLM 回答: %s", e)
            prompt = req.message

        resp = await gateway.complete(
            prompt=prompt,
            task_type="knowledge_qa",
            temperature=0.5,
            max_tokens=2048,
        )
        return ChatResponse(
            intent="knowledge_qa",
            confidence=intent_result.confidence,
            message=resp.content,
            session_id=req.session_id,
        )

    elif intent == IntentType.COMPLEX_GENERATION:
        # 创建异步生成任务
        from app.task_manager import task_manager

        await task_manager.create_task(
            prd_raw=req.message,
            workspace_id=req.workspace_id,
        )
        return ChatResponse(
            intent="complex_generation",
            confidence=intent_result.confidence,
            message="已创建生成任务",
            session_id=req.session_id,
        )

    else:
        # clarification / 其他 → 直接回答
        resp = await gateway.complete(
            prompt=req.message,
            task_type="default",
        )
        return ChatResponse(
            intent="clarification",
            confidence=intent_result.confidence,
            message=resp.content,
            session_id=req.session_id,
        )
