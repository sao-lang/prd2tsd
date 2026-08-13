"""统一交互入口（Block E B1）单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.api.routes.interact import _classify_intent, _load_document_text
from app.api.schemas.interact import InteractRequest, InteractResponse
from app.orchestrator.intent_classifier import IntentClassifier, IntentResult, IntentType
from app.orchestrator.nodes.intent_classify import IntentClassifyNode
from app.orchestrator.state import make_initial_state


class TestInteractSchema:
    """InteractRequest / InteractResponse 模型校验。"""

    def test_request_defaults(self) -> None:
        """验证请求默认值。"""
        req = InteractRequest(message="你好")
        assert req.stream is False
        assert req.doc_id == ""
        assert req.url == ""
        assert req.prd_type == "md"

    def test_request_rejects_invalid_prd_type(self) -> None:
        """验证非法 prd_type 被拒绝。"""
        with pytest.raises(Exception):
            InteractRequest(message="生成", prd_type="exe")

    def test_response_model(self) -> None:
        """验证响应模型默认值。"""
        resp = InteractResponse(intent="chat", confidence=0.9, message="hi")
        assert resp.task_id == ""
        assert resp.session_id == ""


class TestDocumentAnalysisIntent:
    """document_analysis 意图识别。"""

    @pytest.mark.asyncio
    async def test_rule_based_chinese(self) -> None:
        """验证中文文档分析关键词。"""
        classifier = IntentClassifier()
        result = await classifier.classify("分析这份文档的内容")
        assert result.intent == IntentType.DOCUMENT_ANALYSIS

    @pytest.mark.asyncio
    async def test_rule_based_summarize(self) -> None:
        """验证总结关键词。"""
        classifier = IntentClassifier()
        result = await classifier.classify("总结这个文档")
        assert result.intent == IntentType.DOCUMENT_ANALYSIS

    @pytest.mark.asyncio
    async def test_rule_based_english(self) -> None:
        """验证英文关键词。"""
        classifier = IntentClassifier()
        result = await classifier.classify("analyze this document")
        assert result.intent == IntentType.DOCUMENT_ANALYSIS

    @pytest.mark.asyncio
    async def test_url_strong_signal(self) -> None:
        """验证携带 url 时强信号判定为文档分析。"""
        req = InteractRequest(message="帮我看看", url="https://example.com/doc")
        result = await _classify_intent(req)
        assert result.intent == IntentType.DOCUMENT_ANALYSIS
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_doc_id_strong_signal(self) -> None:
        """验证携带 doc_id 时强信号判定为文档分析。"""
        req = InteractRequest(message="分析这个", doc_id="doc-1")
        result = await _classify_intent(req)
        assert result.intent == IntentType.DOCUMENT_ANALYSIS


class TestClassifyNodeIdempotent:
    """classify 节点幂等性 — 统一入口已分类时跳过。"""

    @pytest.mark.asyncio
    async def test_skips_when_intent_preset(self) -> None:
        """验证 state 已含 intent 时跳过分类。"""
        node = IntentClassifyNode(classifier=AsyncMock())
        state = make_initial_state(task_id="t1", prd_raw="hello")
        state["intent"] = IntentType.CHAT.value
        result = await node.run(state)
        assert result["intent"] == "chat"
        node._classifier.classify.assert_not_awaited()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_classifies_when_intent_missing(self) -> None:
        """验证无 intent 时正常分类并写入 state。"""
        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = IntentResult(intent=IntentType.CHAT, confidence=0.8)
        node = IntentClassifyNode(classifier=mock_classifier)
        state = make_initial_state(task_id="t1", prd_raw="你好")
        result = await node.run(state)
        assert result["intent"] == "chat"
        assert result["intent_confidence"] == 0.8
        mock_classifier.classify.assert_awaited_once()


class TestLoadDocumentText:
    """_load_document_text — doc_id 文档分析读取真实内容（Block E B1 断点修复）。

    修复前：复用预览占位，PDF/docx 分析读到 "[PDF 文件，大小 N 字节]" 而非正文。
    修复后：下载原始字节 → multi_format_loader.extract_text 按格式提取。
    """

    @pytest.mark.asyncio
    async def test_loads_markdown_content(self) -> None:
        """md 文档：返回按格式提取的真实文本。"""
        with patch("app.api.routes.interact._try_get_db_session", return_value=AsyncMock()), \
                patch("app.api.routes.interact.document_service") as mock_svc:
            mock_svc.get_document_content = AsyncMock(
                return_value=("# 标题\n正文".encode(), "doc.md"),
            )
            text, source = await _load_document_text(
                InteractRequest(message="分析", doc_id="doc-1"),
            )
        assert "# 标题\n正文" in text
        assert "doc.md" in source

    @pytest.mark.asyncio
    async def test_loads_csv_content_full(self) -> None:
        """csv 文档：返回完整行级文本（不受预览前 20 行截断）。"""
        content = "a,b\n" + "\n".join(f"{i},v{i}" for i in range(50))
        with patch("app.api.routes.interact._try_get_db_session", return_value=AsyncMock()), \
                patch("app.api.routes.interact.document_service") as mock_svc:
            mock_svc.get_document_content = AsyncMock(return_value=(content.encode(), "data.csv"))
            text, _ = await _load_document_text(
                InteractRequest(message="分析", doc_id="doc-1"),
            )
        assert "记录: 49，v49。" in text  # 第 50 行数据也应包含（不截断）
        assert text.count("记录:") == 51  # header + 50 行数据

    @pytest.mark.asyncio
    async def test_loads_pdf_via_extract_not_placeholder(self) -> None:
        """pdf 文档：走多格式提取返回真实文本，而非预览占位符。"""
        with patch("app.api.routes.interact._try_get_db_session", return_value=AsyncMock()), \
                patch("app.api.routes.interact.document_service") as mock_svc, \
                patch(
                    "app.knowledge_layer.ingestion.multi_format_loader.extract_text",
                    return_value="PDF 真实正文内容",
                ):
            mock_svc.get_document_content = AsyncMock(return_value=(b"%PDF-fake", "spec.pdf"))
            text, _ = await _load_document_text(
                InteractRequest(message="分析", doc_id="doc-1"),
            )
        assert text == "PDF 真实正文内容"
        assert "PDF 文件，大小" not in text  # 不再返回预览占位符

    @pytest.mark.asyncio
    async def test_returns_not_found(self) -> None:
        """文档不存在时返回错误信息。"""
        with patch("app.api.routes.interact._try_get_db_session", return_value=AsyncMock()), \
                patch("app.api.routes.interact.document_service") as mock_svc:
            mock_svc.get_document_content = AsyncMock(return_value=None)
            text, source = await _load_document_text(
                InteractRequest(message="分析", doc_id="missing"),
            )
        assert text == ""
        assert "不存在" in source

    @pytest.mark.asyncio
    async def test_returns_extract_failure(self) -> None:
        """提取失败时返回错误信息而非崩溃。"""
        with patch("app.api.routes.interact._try_get_db_session", return_value=AsyncMock()), \
                patch("app.api.routes.interact.document_service") as mock_svc, \
                patch(
                    "app.knowledge_layer.ingestion.multi_format_loader.extract_text",
                    side_effect=ValueError("不支持的格式: .exe"),
                ):
            mock_svc.get_document_content = AsyncMock(return_value=(b"xx", "doc.exe"))
            text, source = await _load_document_text(
                InteractRequest(message="分析", doc_id="doc-1"),
            )
        assert text == ""
        assert "提取失败" in source
