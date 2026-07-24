"""块 E — Web 索引集成测试（E7：WebLoader/WebCrawler/WebSync）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.web_indexing.web_crawler import WebCrawler
from app.web_indexing.web_loader import WebLoader
from app.web_indexing.web_sync import WebSyncScheduler

# ── 模拟 HTML 页面 ──

MOCK_HTML = """<!DOCTYPE html>
<html><head><title>Test Page</title></head>
<body>
<article>
<h1>Test Article</h1>
<p>This is a test paragraph about technology stack.</p>
<a href="/page1">Page 1</a>
<a href="/page2">Page 2</a>
</article>
</body></html>
"""

MOCK_PAGE1_HTML = """<!DOCTYPE html>
<html><head><title>Page 1</title></head>
<body><p>Content of page 1 about machine learning.</p></body></html>
"""

MOCK_PAGE2_HTML = """<!DOCTYPE html>
<html><head><title>Page 2</title></head>
<body><p>Content of page 2 about data processing.</p></body></html>
"""


class MockResponse:
    """模拟 httpx 响应。"""

    def __init__(self, html: str, status_code: int = 200) -> None:
        self._html = html
        self.status_code = status_code
        self.headers = {"content-type": "text/html"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    @property
    def text(self) -> str:
        return self._html


@pytest.mark.asyncio
async def test_web_loader_fetch_and_extract() -> None:
    """验证 WebLoader 抓取并提取正文。"""
    loader = WebLoader()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MockResponse(MOCK_HTML))):
        result = await loader.fetch("https://example.com")

    assert result["status_code"] == 200
    assert result["title"] == "Test Page"
    assert result["text_content"]
    assert "Test Article" in result["content"]


@pytest.mark.asyncio
async def test_web_loader_timeout_returns_error() -> None:
    """验证超时场景返回错误信息。"""
    loader = WebLoader()

    async def _mock_timeout(*args, **kwargs) -> MockResponse:  # noqa: ANN002, ANN003
        import httpx
        raise httpx.TimeoutException("timeout")

    with patch("httpx.AsyncClient.get", new=_mock_timeout):
        result = await loader.fetch("https://example.com")

    assert result["error"] is not None
    assert "超时" in result["error"]


@pytest.mark.asyncio
async def test_web_crawler_extract_links() -> None:
    """验证 WebCrawler 链接提取。"""
    links = WebCrawler._extract_links(
        MOCK_HTML,
        "https://example.com",
    )
    assert "https://example.com/page1" in links
    assert "https://example.com/page2" in links


@pytest.mark.asyncio
async def test_web_crawler_robots_txt_disallow() -> None:
    """验证 robots.txt 规则过滤。"""
    assert WebCrawler._is_disallowed(
        "https://example.com/admin",
        ["/admin"],
        "https://example.com",
    ) is True
    assert WebCrawler._is_disallowed(
        "https://example.com/public",
        ["/admin"],
        "https://example.com",
    ) is False


@pytest.mark.asyncio
async def test_web_sync_track_and_clear() -> None:
    """验证 WebSyncScheduler URL 跟踪。"""
    sync = WebSyncScheduler()
    assert sync.get_tracked_urls() == []

    sync._tracked["https://example.com"] = {"etag": '"abc123"'}
    tracked = sync.get_tracked_urls()
    assert "https://example.com" in tracked

    sync.clear()
    assert sync.get_tracked_urls() == []


@pytest.mark.asyncio
async def test_web_sync_track_state() -> None:
    """验证跟踪状态管理。"""
    sync = WebSyncScheduler()

    # 初始跟踪
    sync._tracked["https://example.com"] = {"etag": '"abc"', "content_hash": "hash1"}
    assert sync.get_tracked_urls() == ["https://example.com"]

    # 跟踪后清除
    sync.clear()
    assert sync.get_tracked_urls() == []

    # 再次跟踪
    sync._tracked["https://example.com/a"] = {"etag": '"xyz"'}
    sync._tracked["https://example.com/b"] = {"etag": '"uvw"'}
    assert len(sync.get_tracked_urls()) == 2
