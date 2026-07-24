"""Web 索引模块单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.web_indexing.search_fallback import SearchFallback
from app.web_indexing.web_crawler import WebCrawler
from app.web_indexing.web_loader import WebLoader
from app.web_indexing.web_sync import WebSyncScheduler


class TestWebLoader:
    """Web 加载器单元测试。"""

    def test_extract_title(self) -> None:
        """验证 HTML 标题提取。"""
        loader = WebLoader()
        title = loader._extract_title("<html><head><title>测试页面</title></head><body></body></html>")
        assert title == "测试页面"

    def test_extract_title_empty(self) -> None:
        """验证无标题时返回空。"""
        loader = WebLoader()
        title = loader._extract_title("<html><body></body></html>")
        assert title == ""

    def test_extract_text(self) -> None:
        """验证纯文本提取。"""
        loader = WebLoader()
        html = "<html><body><p>Hello World</p></body></html>"
        text = loader._extract_text(html)
        assert "Hello World" in text

    def test_extract_text_strips_scripts(self) -> None:
        """验证移除 script 标签。"""
        loader = WebLoader()
        html = "<html><body><script>alert(1)</script><p>内容</p></body></html>"
        text = loader._extract_text(html)
        assert "alert" not in text
        assert "内容" in text

    def test_html_to_markdown_simple(self) -> None:
        """验证 HTML 转 Markdown。"""
        loader = WebLoader()
        html = "<h1>标题</h1><p>段落</p><a href='https://example.com'>链接</a>"
        md = loader._html_to_markdown_simple(html, "测试")
        assert "# 测试" in md
        assert "标题" in md
        assert "段落" in md
        assert "[链接](https://example.com)" in md


class TestWebCrawler:
    """Web 爬虫单元测试。"""

    def test_extract_links(self) -> None:
        """验证链接提取。"""
        html = '<html><body><a href="/page1">P1</a><a href="https://other.com">外部</a></body></html>'
        links = WebCrawler._extract_links(html, "https://example.com")
        assert "https://example.com/page1" in links
        assert "https://other.com" not in links

    def test_extract_links_ignores_javascript(self) -> None:
        """验证忽略 javascript: 链接。"""
        html = '<html><body><a href="javascript:void(0)">JS</a></body></html>'
        links = WebCrawler._extract_links(html, "https://example.com")
        assert len(links) == 0

    def test_is_disallowed(self) -> None:
        """验证 robots.txt 规则检查。"""
        assert WebCrawler._is_disallowed("https://example.com/admin", ["/admin"], "https://example.com") is True
        assert WebCrawler._is_disallowed("https://example.com/public", ["/admin"], "https://example.com") is False
        assert WebCrawler._is_disallowed("https://example.com/page", [], "https://example.com") is False


class TestWebSync:
    """Web 同步单元测试。"""

    def test_tracked_urls(self) -> None:
        """验证 URL 跟踪。"""
        sync = WebSyncScheduler()
        assert sync.get_tracked_urls() == []
        # 模拟同步后跟踪
        sync._tracked["https://example.com"] = {"etag": "abc123"}
        assert "https://example.com" in sync.get_tracked_urls()

    def test_clear(self) -> None:
        """验证清除跟踪状态。"""
        sync = WebSyncScheduler()
        sync._tracked["https://example.com"] = {"etag": "abc"}
        sync.clear()
        assert sync.get_tracked_urls() == []


class TestSearchFallback:
    """搜索回退单元测试。"""

    @pytest.mark.asyncio
    async def test_should_fallback_when_few_results(self) -> None:
        """验证本地结果少时触发回退。"""
        fallback = SearchFallback()
        assert await fallback.should_fallback([]) is True
        assert await fallback.should_fallback([1]) is True
        assert await fallback.should_fallback([1, 2]) is True

    @pytest.mark.asyncio
    async def test_should_not_fallback_when_enough_results(self) -> None:
        """验证本地结果足够时不触发回退。"""
        fallback = SearchFallback()
        assert await fallback.should_fallback([1, 2, 3]) is False
        assert await fallback.should_fallback([1, 2, 3, 4, 5]) is False

    def test_parse_html_results_empty(self) -> None:
        """验证空 HTML 返回空列表。"""
        results = SearchFallback._parse_html_results("<html></html>", 5)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_generate_keywords_with_llm(self) -> None:
        """验证 LLM 关键词生成。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "optimized search keywords"
        mock_llm.complete = AsyncMock(return_value=mock_resp)

        fallback = SearchFallback(llm_gateway=mock_llm)
        keywords = await fallback.generate_search_keywords("原始查询")
        assert keywords == "optimized search keywords"

    @pytest.mark.asyncio
    async def test_generate_keywords_without_llm(self) -> None:
        """验证无 LLM 时降级。"""
        fallback = SearchFallback(llm_gateway=None)
        keywords = await fallback.generate_search_keywords("原始查询")
        assert keywords == "原始查询"

    @pytest.mark.asyncio
    async def test_search_and_index_with_vector_store(self) -> None:
        """验证 search_and_index 向量存储索引。"""
        fallback = SearchFallback(llm_gateway=None)

        mock_vs = MagicMock()
        mock_vs.ensure_extensions = AsyncMock()
        mock_vs.upsert_chunk = AsyncMock()

        # Mock search() 方法绕过真实 HTTP 调用
        mock_results = [
            {"title": "Result 1", "url": "https://example.com/1", "snippet": "Snippet 1"},
        ]
        with patch.object(fallback, "search", new=AsyncMock(return_value=mock_results)):
            results = await fallback.search_and_index(
                query="test",
                workspace_id="ws-1",
                max_results=5,
                vector_store=mock_vs,
            )

        assert len(results) == 1
        mock_vs.ensure_extensions.assert_awaited_once()
        mock_vs.upsert_chunk.assert_awaited_once()


class TestWebhook:
    """Webhook 单元测试。"""

    def test_register_and_unregister(self) -> None:
        """验证 Webhook 注册和注销。"""
        from app.integrations.webhook import IntegrationHub

        hub = IntegrationHub()
        hub.register_webhook("ws-1", "https://example.com/hook", "task.completed")
        assert hub.get_webhook_url("ws-1", "task.completed") == "https://example.com/hook"

        hub.unregister_webhook("ws-1", "task.completed")
        assert hub.get_webhook_url("ws-1", "task.completed") is None

    def test_unregister_nonexistent(self) -> None:
        """验证注销不存在的 Webhook 返回 False。"""
        from app.integrations.webhook import IntegrationHub

        hub = IntegrationHub()
        assert hub.unregister_webhook("ws-x", "task.completed") is False
