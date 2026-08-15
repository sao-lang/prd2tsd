"""统一交互入口 — 对话 / 提问 / 文档分析 / 复杂生成 单一入口（Block E B1）。

Block E 整改核心：将 chat / knowledge_qa / complex_generation /
document_analysis 合并为 POST /api/v1/interact，服务端按意图识别分流。

意图处理：
- chat / knowledge_qa / clarification → 主编排图（图内 classify 节点幂等跳过）
- complex_generation → 异步任务（同步返回 task_id / 流式 SSE task.* 事件）
- document_analysis → 文档分析（doc_id 读已上传文档 / url 抓取，同步摘要 / 流式 SSE）

流式模式：stream=true 统一返回 text/event-stream，复用 E12 EventBus。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_orchestrator
from app.api.schemas.interact import InteractRequest, InteractResponse
from app.auth.deps import get_current_user
from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.document_management.service import document_service
from app.llm_gateway import gateway as default_gateway
from app.models.user import User
from app.orchestrator.intent_classifier import IntentClassifier, IntentResult, IntentType
from app.orchestrator.state import make_initial_state
from app.streaming.models import SseEvent
from app.streaming.sse import sse_response, subscribe_task_events
from app.web_indexing.url_security import UrlSecurityError

logger = get_logger("prd2tsd.interact")

router = APIRouter(prefix="/api/v1", tags=["interact"])

# 共享意图分类器单例 — 统一交互入口为唯一判定来源，
# 消除"路由手动分类 vs 图内 classify 节点"的双实现问题。
classifier = IntentClassifier(llm_gateway=default_gateway)


def _try_get_db_session() -> AsyncSession | None:
    """尝试获取数据库会话；未注册或未连接时返回 None（文档分析降级）。

    Returns:
        AsyncSession 实例；连接不可用时返回 None。
    """
    try:
        connector = connection_manager.get("postgres")
        return connector.get_session()  # type: ignore[attr-defined, no-any-return]
    except Exception:
        return None


async def _classify_intent(req: InteractRequest) -> IntentResult:
    """意图识别 — URL/doc_id 强信号优先，其次规则 + LLM 两级分类。

    Args:
        req: InteractRequest 请求体。

    Returns:
        意图分类结果。
    """
    # 请求携带 url / doc_id 时，强信号判定为文档分析
    if req.url or req.doc_id:
        return IntentResult(
            intent=IntentType.DOCUMENT_ANALYSIS,
            confidence=0.9,
            explanation="请求携带 url/doc_id，判定为文档分析",
        )
    return await classifier.classify(user_input=req.message)


@router.post("/interact")
async def interact(
    req: InteractRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    orchestrator: Any = Depends(get_orchestrator),
) -> Response:
    """统一交互入口。

    按意图识别结果分流（详见模块 docstring）。

    Args:
        req: InteractRequest 请求体。
        request: FastAPI 请求（工作空间上下文）。
        current_user: 当前用户。
        orchestrator: 主编排器实例。

    Returns:
        同步模式返回 InteractResponse（JSON）；流式模式返回 StreamingResponse。
    """
    intent_result = await _classify_intent(req)

    # 流式模式
    if req.stream:
        return _route_stream(req, intent_result, current_user, orchestrator, request)

    # 同步模式
    resp = await _route_sync(req, intent_result, current_user, orchestrator, request)
    return JSONResponse(content=resp.model_dump())


# ── 同步模式 ──


async def _route_sync(
    req: InteractRequest,
    intent_result: IntentResult,
    current_user: User,
    orchestrator: Any,
    request: Request,
) -> InteractResponse:
    """同步模式分发。

    Args:
        req: InteractRequest 请求体。
        intent_result: 意图分类结果。
        current_user: 当前用户。
        orchestrator: 主编排器实例。
        request: FastAPI 请求（工作空间上下文）。

    Returns:
        InteractResponse 响应体。
    """
    intent = intent_result.intent

    if intent == IntentType.DOCUMENT_ANALYSIS:
        return await _document_analysis_sync(req, request, current_user, orchestrator)

    if intent == IntentType.COMPLEX_GENERATION:
        task_id = await _create_generation_task(req, current_user, orchestrator)
        return InteractResponse(
            intent=IntentType.COMPLEX_GENERATION.value,
            confidence=intent_result.confidence,
            message=f"已创建生成任务: {task_id}",
            task_id=task_id,
            session_id=req.session_id,
        )

    # chat / knowledge_qa / clarification → 主编排图同步执行
    return await _graph_sync(req, intent_result, orchestrator)


async def _graph_sync(
    req: InteractRequest,
    intent_result: IntentResult,
    orchestrator: Any,
) -> InteractResponse:
    """通过主编排图同步执行 chat / knowledge_qa / clarification。

    将 intent 预写入初始 state，使图内 classify 节点幂等跳过（消除双实现）。

    Args:
        req: InteractRequest 请求体。
        intent_result: 意图分类结果。
        orchestrator: 主编排器实例。

    Returns:
        InteractResponse 响应体。
    """
    task_id = str(uuid.uuid4())
    initial_state = make_initial_state(
        task_id=task_id,
        prd_raw=req.message,
        prd_file_type=req.prd_type,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
    )
    # 预写入意图，图内 classify 节点检测到后跳过分类
    initial_state["intent"] = intent_result.intent.value
    initial_state["intent_confidence"] = intent_result.confidence
    initial_state["intent_sub"] = intent_result.sub_intent

    config = {"configurable": {"thread_id": task_id}}

    try:
        final_state = await orchestrator.ainvoke(initial_state, config)
        chat_response = final_state.get("chat_response", "") if isinstance(final_state, dict) else ""
        status = final_state.get("status", "complete") if isinstance(final_state, dict) else "complete"

        return InteractResponse(
            intent=intent_result.intent.value,
            confidence=intent_result.confidence,
            message=chat_response or f"处理完成 (status={status})",
            session_id=req.session_id,
        )
    except Exception as exc:
        logger.exception("LangGraph 图执行失败: %s", exc)
        # 降级：直接 LLM 回答
        resp = await default_gateway.complete(
            prompt=req.message,
            task_type="chat",
            temperature=0.7,
            max_tokens=1024,
        )
        return InteractResponse(
            intent="chat",
            confidence=0.5,
            message=resp.content,
            session_id=req.session_id,
        )


async def _create_generation_task(
    req: InteractRequest,
    current_user: User,
    orchestrator: Any,
    prd_raw: str | None = None,
) -> str:
    """创建异步复杂生成任务。

    Args:
        req: InteractRequest 请求体。
        current_user: 当前用户。
        orchestrator: 主编排器实例。
        prd_raw: 覆盖 PRD 内容（URL 一键生成时传入抓取文本）。

    Returns:
        任务 ID。
    """
    from app.task_manager import task_manager

    user_role = ""
    if current_user.team_memberships:
        first_membership = current_user.team_memberships[0]
        user_role = (
            getattr(first_membership.role, "name", "")
            if hasattr(first_membership, "role")
            else ""
        )

    task_id = await task_manager.create_task(
        prd_raw=prd_raw or req.message,
        prd_file_type=req.prd_type,
        workspace_id=req.workspace_id,
        user_id=str(current_user.id),
        user_role=user_role,
        session_id=req.session_id,
        orchestrator=orchestrator,
    )
    return task_id


# ── 文档分析（document_analysis 意图）──


async def _load_document_text(req: InteractRequest) -> tuple[str, str]:
    """读取已上传文档文本（doc_id 路径）。

    通过 storage 下载原始字节，再用 multi_format_loader 按格式提取文本，
    避免 PDF/docx 走预览占位导致分析读不到真实内容（Block E B1 断点修复）。

    Args:
        req: InteractRequest 请求体。

    Returns:
        (文本内容, 来源描述)；文本为空表示读取失败。
    """
    from app.knowledge_layer.ingestion.multi_format_loader import extract_text

    session = _try_get_db_session()
    if session is None:
        return "", "数据库连接不可用，无法读取文档"
    try:
        content = await document_service.get_document_content(session, req.doc_id)
        if content is None:
            return "", f"文档不存在: {req.doc_id}"
        raw, filename = content
        try:
            text = extract_text(raw, filename)
        except ValueError as exc:
            return "", f"文档内容提取失败: {exc}"
        if not text.strip():
            return "", f"文档无可分析文本: {filename}"
        return text, f"文档 {req.doc_id}（{filename}）"
    finally:
        await session.close()


def _build_document_prompt(text: str, instruction: str, source_label: str) -> str:
    """构造文档分析提示词。

    Args:
        text: 文档文本。
        instruction: 用户分析指令。
        source_label: 文档来源描述。

    Returns:
        LLM 提示词。
    """
    truncated = text[:12000]
    return (
        "你是文档分析助手。请根据用户指令分析给定的文档内容，输出结构化结论。\n\n"
        f"文档来源：{source_label}\n\n"
        f"用户指令：{instruction or '请总结这份文档'}\n\n"
        f"文档内容：\n{truncated}\n\n"
        "请给出清晰、准确、结构化的分析结果。"
    )


async def _analyze_document(text: str, instruction: str, source_label: str) -> str:
    """对文档文本执行分析/总结（LLM 同步）。

    Args:
        text: 文档文本。
        instruction: 用户分析指令。
        source_label: 文档来源描述。

    Returns:
        分析结果文本。
    """
    resp = await default_gateway.complete(
        prompt=_build_document_prompt(text, instruction, source_label),
        task_type="document_analysis",
        temperature=0.3,
        max_tokens=2048,
    )
    return resp.content


def _effective_workspace_id(req: InteractRequest, request: Request) -> str:
    """获取有效工作空间 ID（请求体优先，其次请求上下文）。

    Args:
        req: InteractRequest 请求体。
        request: FastAPI 请求。

    Returns:
        工作空间 ID（可能为空）。
    """
    if req.workspace_id:
        return req.workspace_id
    from app.auth.middleware import _SCOPE_WS_ID as _SCOPE_WORKSPACE_ID

    return request.scope.get(_SCOPE_WORKSPACE_ID) or ""


async def _fetch_url_for_analysis(url: str) -> tuple[str, str]:
    """SSRF 校验并抓取 URL → (文本, 来源标识)。

    Args:
        url: 目标 URL。

    Returns:
        (文本内容, 来源描述)。

    Raises:
        UrlSecurityError: URL 非法 / 指向内网 / 抓取失败。
    """
    from app.web_indexing.url_document import UrlDocumentService

    try:
        fetched = await UrlDocumentService().fetch_content(url)
    except (UrlSecurityError, ValueError) as exc:
        raise UrlSecurityError(str(exc)) from exc
    text = (fetched.get("text_content") or "").strip()
    if not text:
        text = (fetched.get("content") or "").strip()
    return text, fetched.get("title") or fetched.get("validated_url") or url


async def _ingest_url_document(
    req: InteractRequest,
    request: Request,
    current_user: User,
) -> tuple[str, str]:
    """URL → 抓取 → 入库 → (文本, 来源标识)。

    Args:
        req: InteractRequest 请求体。
        request: FastAPI 请求。
        current_user: 当前用户。

    Returns:
        (文本内容, 来源描述)。

    Raises:
        ValueError: 工作空间缺失 / 数据库不可用 / 抓取失败。
    """
    from app.web_indexing.url_document import UrlDocumentService

    ws_id = _effective_workspace_id(req, request)
    session = _try_get_db_session()
    if session is None:
        raise ValueError("数据库连接不可用，无法入库 URL 文档")
    try:
        svc = UrlDocumentService()
        fetched = await svc.fetch_content(req.url)
        text = (fetched.get("text_content") or "").strip()
        if not text:
            text = (fetched.get("content") or "").strip()
        upload = await svc.ingest(
            session,
            ws_id,
            str(current_user.id),
            req.url,
            session_id=req.session_id or None,
            fetched=fetched,
        )
        source = f"文档 {upload.document.id}（来源 {fetched.get('validated_url') or req.url}）"
        return text, source
    finally:
        await session.close()


async def _create_generation_task_from_url(
    req: InteractRequest,
    request: Request,
    current_user: User,
    orchestrator: Any,
) -> str:
    """URL → 抓取 → 创建复杂生成任务（一键生成 TSD）。

    Args:
        req: InteractRequest 请求体。
        request: FastAPI 请求。
        current_user: 当前用户。
        orchestrator: 主编排器实例。

    Returns:
        任务 ID。

    Raises:
        UrlSecurityError / ValueError: 抓取失败或内容为空。
    """
    text, _ = await _fetch_url_for_analysis(req.url)
    if not text:
        raise ValueError("URL 内容为空，无法生成")
    return await _create_generation_task(req, current_user, orchestrator, prd_raw=text)


async def _document_analysis_sync(
    req: InteractRequest,
    request: Request,
    current_user: User,
    orchestrator: Any,
) -> InteractResponse:
    """文档分析 — 同步模式。

    分发：
    - generate=true + url → 抓取 → 创建复杂生成任务（返回 task_id）
    - url → 抓取 → 入库 → 分析摘要
    - doc_id → 读取 → 分析摘要

    Args:
        req: InteractRequest 请求体。
        request: FastAPI 请求。
        current_user: 当前用户。
        orchestrator: 主编排器实例。

    Returns:
        InteractResponse 响应体。
    """
    if not req.url and not req.doc_id:
        return InteractResponse(
            intent=IntentType.DOCUMENT_ANALYSIS.value,
            confidence=0.8,
            message="请提供 doc_id 或 url 以进行文档分析",
            session_id=req.session_id,
        )

    # 一键生成 TSD
    if req.generate:
        if not req.url:
            return InteractResponse(
                intent=IntentType.DOCUMENT_ANALYSIS.value,
                confidence=0.8,
                message="一键生成 TSD 需要提供 url",
                session_id=req.session_id,
            )
        try:
            task_id = await _create_generation_task_from_url(req, request, current_user, orchestrator)
        except (UrlSecurityError, ValueError) as exc:
            return InteractResponse(
                intent=IntentType.DOCUMENT_ANALYSIS.value,
                confidence=0.8,
                message=str(exc),
                session_id=req.session_id,
            )
        return InteractResponse(
            intent=IntentType.COMPLEX_GENERATION.value,
            confidence=0.9,
            message=f"已基于 URL 内容创建生成任务: {task_id}",
            task_id=task_id,
            session_id=req.session_id,
        )

    # URL：抓取 → 入库 → 分析
    if req.url:
        try:
            text, source_label = await _ingest_url_document(req, request, current_user)
        except (UrlSecurityError, ValueError) as exc:
            return InteractResponse(
                intent=IntentType.DOCUMENT_ANALYSIS.value,
                confidence=0.8,
                message=str(exc),
                session_id=req.session_id,
            )
        if not text:
            return InteractResponse(
                intent=IntentType.DOCUMENT_ANALYSIS.value,
                confidence=0.8,
                message=f"无法读取内容: {source_label}",
                session_id=req.session_id,
            )
        summary = await _analyze_document(text, req.message, source_label)
        return InteractResponse(
            intent=IntentType.DOCUMENT_ANALYSIS.value,
            confidence=0.8,
            message=summary,
            session_id=req.session_id,
        )

    # doc_id：读取 → 分析
    text, source_label = await _load_document_text(req)
    if not text:
        return InteractResponse(
            intent=IntentType.DOCUMENT_ANALYSIS.value,
            confidence=0.8,
            message=f"无法读取内容: {source_label}",
            session_id=req.session_id,
        )
    summary = await _analyze_document(text, req.message, source_label)
    return InteractResponse(
        intent=IntentType.DOCUMENT_ANALYSIS.value,
        confidence=0.8,
        message=summary,
        session_id=req.session_id,
    )


# ── 流式模式 ──


def _route_stream(
    req: InteractRequest,
    intent_result: IntentResult,
    current_user: User,
    orchestrator: Any,
    request: Request,
) -> StreamingResponse:
    """流式模式分发。

    Args:
        req: InteractRequest 请求体。
        intent_result: 意图分类结果。
        current_user: 当前用户。
        orchestrator: 主编排器实例。
        request: FastAPI 请求。

    Returns:
        StreamingResponse 实例。
    """
    intent = intent_result.intent

    if intent == IntentType.DOCUMENT_ANALYSIS:
        if not req.url and not req.doc_id:
            return _single_message_stream("请提供 doc_id 或 url 以进行文档分析")
        return _document_analysis_stream(req, request, current_user, orchestrator)

    if intent == IntentType.COMPLEX_GENERATION:
        return _generation_stream(req, current_user, orchestrator)

    # chat / knowledge_qa / clarification → SSE 流式回答
    return _chat_qa_stream(req, intent_result)


def _single_message_stream(message: str) -> StreamingResponse:
    """生成单条消息 SSE 事件流（澄清等场景）。

    Args:
        message: 提示消息。

    Returns:
        StreamingResponse 实例。
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        yield SseEvent(
            type="qna.status",
            payload={"phase": "complete", "message": message},
        ).to_sse_line()
        yield SseEvent.done(task_id="").to_sse_line()

    return sse_response(event_generator())


def _chat_qa_stream(
    req: InteractRequest,
    intent_result: IntentResult,
) -> StreamingResponse:
    """对话 / 提问 / 澄清 — SSE 流式（知识检索 + LLM chunk）。

    Args:
        req: InteractRequest 请求体。
        intent_result: 意图分类结果。

    Returns:
        StreamingResponse 实例。
    """
    query = req.message
    workspace_id = req.workspace_id

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # 知识检索（knowledge_qa 意图）
            context = ""
            if intent_result.intent == IntentType.KNOWLEDGE_QA:
                yield SseEvent(
                    type="qna.status",
                    payload={"phase": "retrieving", "message": "正在检索知识图谱..."},
                ).to_sse_line()
                try:
                    from app.knowledge_layer.pipeline import RetrievalPipeline

                    pipeline = RetrievalPipeline()
                    retrieval_result = await pipeline.retrieve(
                        query=query,
                        workspace_id=workspace_id,
                        top_k=5,
                    )
                    context_parts: list[str] = []
                    if retrieval_result.global_summary:
                        context_parts.append(retrieval_result.global_summary)
                    for doc in retrieval_result.results[:5]:
                        context_parts.append(doc.text)
                    context = "\n---\n".join(context_parts)
                    sources = [{"id": r.id, "score": r.score} for r in retrieval_result.results[:5]]

                    yield SseEvent(
                        type="qna.status",
                        payload={
                            "phase": "retrieved",
                            "message": f"检索到 {len(sources)} 条相关结果",
                            "sources": sources,
                        },
                    ).to_sse_line()
                except Exception:
                    yield SseEvent(
                        type="qna.status",
                        payload={"phase": "retrieved", "message": "未找到知识库内容，将直接回答"},
                    ).to_sse_line()

            # LLM 流式生成
            yield SseEvent(
                type="qna.status",
                payload={"phase": "generating", "message": "正在生成回答..."},
            ).to_sse_line()

            if context:
                prompt = (
                    "请基于以下上下文回答用户问题。\n\n"
                    f"上下文：\n{context}\n\n"
                    f"用户问题：{query}\n\n"
                    "请给出清晰、准确的回答。"
                )
            else:
                prompt = query

            async for chunk in default_gateway.stream_complete(
                prompt=prompt,
                task_type="qna.answer",
                workspace_id=workspace_id,
                layer="qna",
                node="stream_answer",
            ):
                yield SseEvent(type="qna.chunk", payload={"content": chunk}).to_sse_line()

            yield SseEvent(
                type="qna.status",
                payload={"phase": "complete", "message": "回答完成"},
            ).to_sse_line()
            yield SseEvent.done(task_id="").to_sse_line()
        except Exception as exc:
            yield SseEvent.error(
                message=f"Q&A 处理出错: {exc}",
                code="qna_error",
            ).to_sse_line()

    return sse_response(event_generator())


def _generation_stream(
    req: InteractRequest,
    current_user: User,
    orchestrator: object,
) -> StreamingResponse:
    """复杂生成 — SSE 全程推送（task.* 事件）。

    Args:
        req: InteractRequest 请求体。
        current_user: 当前用户。
        orchestrator: 主编排器实例。

    Returns:
        StreamingResponse 实例。
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            task_id = await _create_generation_task(req, current_user, orchestrator)
            channel = f"task:{task_id}"
            created_event = SseEvent(
                type="task.created",
                payload={"task_id": task_id, "status": "running"},
            )
            async for line in subscribe_task_events(channel, created_event):
                yield line
        except Exception as exc:
            yield SseEvent.error(
                message=f"生成任务创建失败: {exc}",
                code="generation_error",
            ).to_sse_line()

    return sse_response(event_generator())


def _document_analysis_stream(
    req: InteractRequest,
    request: Request,
    current_user: User,
    orchestrator: Any,
) -> StreamingResponse:
    """文档分析 — SSE 流式（analysis.* 事件）。

    分发：
    - generate=true + url → 创建生成任务并订阅 task.* 事件
    - url → 抓取 → 入库 → analysis.* 流式分析
    - doc_id → 读取 → analysis.* 流式分析

    Args:
        req: InteractRequest 请求体。
        request: FastAPI 请求。
        current_user: 当前用户。
        orchestrator: 主编排器实例。

    Returns:
        StreamingResponse 实例。
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            if not req.url and not req.doc_id:
                yield SseEvent.error(
                    message="请提供 doc_id 或 url 以进行文档分析",
                    code="analysis_error",
                ).to_sse_line()
                return

            # 一键生成 TSD：创建生成任务并订阅任务事件
            if req.generate:
                if not req.url:
                    yield SseEvent.error(
                        message="一键生成 TSD 需要提供 url",
                        code="analysis_error",
                    ).to_sse_line()
                    return
                task_id = await _create_generation_task_from_url(req, request, current_user, orchestrator)
                channel = f"task:{task_id}"
                created_event = SseEvent(
                    type="task.created",
                    payload={"task_id": task_id, "status": "running"},
                )
                async for line in subscribe_task_events(channel, created_event):
                    yield line
                return

            yield SseEvent(
                type="analysis.status",
                payload={"phase": "loading", "message": "正在加载文档..."},
            ).to_sse_line()

            if req.url:
                text, source_label = await _ingest_url_document(req, request, current_user)
            else:
                text, source_label = await _load_document_text(req)
            if not text:
                yield SseEvent.error(
                    message=f"无法读取内容: {source_label}",
                    code="analysis_error",
                ).to_sse_line()
                return

            yield SseEvent(
                type="analysis.status",
                payload={"phase": "analyzing", "message": f"正在分析: {source_label}"},
            ).to_sse_line()

            prompt = _build_document_prompt(text, req.message, source_label)
            async for chunk in default_gateway.stream_complete(
                prompt=prompt,
                task_type="document_analysis",
                workspace_id=req.workspace_id,
                layer="analysis",
                node="document_analysis",
            ):
                yield SseEvent(type="analysis.chunk", payload={"content": chunk}).to_sse_line()

            yield SseEvent(
                type="analysis.status",
                payload={"phase": "complete", "message": "分析完成"},
            ).to_sse_line()
            yield SseEvent.done(task_id="").to_sse_line()
        except (UrlSecurityError, ValueError) as exc:
            yield SseEvent.error(
                message=str(exc),
                code="analysis_error",
            ).to_sse_line()
        except Exception as exc:
            yield SseEvent.error(
                message=f"文档分析失败: {exc}",
                code="analysis_error",
            ).to_sse_line()

    return sse_response(event_generator())
