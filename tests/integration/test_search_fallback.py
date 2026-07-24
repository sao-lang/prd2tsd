"""块 E — 搜索引擎回退集成测试（E11：LLM 关键词生成 + 结果索引）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.web_indexing.search_fallback import SearchFallback


class MockLLMResponse:
    """模拟 LLM Gateway 响应。"""

    def __init__(self, content: str) -> None:
        self.content = content


@pytest.mark.asyncio
async def test_search_fallback_should_fallback() -> None:
    """验证本地结果不足时触发回退。"""
    fallback = SearchFallback()
    assert await fallback.should_fallback([]) is True
    assert await fallback.should_fallback([1, 2]) is True
    assert await fallback.should_fallback([1, 2, 3]) is False


@pytest.mark.asyncio
async def test_search_fallback_generate_keywords_with_llm() -> None:
    """验证 LLM 生成搜索关键词（有 LLM Gateway）。"""
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=MockLLMResponse("machine learning neural network"))
    fallback = SearchFallback(llm_gateway=mock_llm)

    keywords = await fallback.generate_search_keywords("How to build a machine learning model")
    assert "neural" in keywords.lower() or "machine" in keywords.lower()


@pytest.mark.asyncio
async def test_search_fallback_generate_keywords_without_llm() -> None:
    """验证无 LLM Gateway 时降级为原始查询。"""
    fallback = SearchFallback(llm_gateway=None)
    keywords = await fallback.generate_search_keywords("test query")
    assert keywords == "test query"


@pytest.mark.asyncio
async def test_search_fallback_generate_keywords_llm_failure() -> None:
    """验证 LLM 失败时降级为原始查询。"""
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM unavailable"))
    fallback = SearchFallback(llm_gateway=mock_llm)

    keywords = await fallback.generate_search_keywords("test query")
    assert keywords == "test query"


@pytest.mark.asyncio
async def test_search_fallback_parse_html_empty() -> None:
    """验证空 HTML 解析。"""
    results = SearchFallback._parse_html_results("<html></html>", 5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_fallback_parse_html_with_results() -> None:
    """验证 HTML 搜索结果解析。"""
    html = """
    <html>
    <body>
    <a rel="nofollow" class="result__a" href="https://example.com/1">Result One</a>
    <a class="result__snippet">This is snippet one</a>
    <a rel="nofollow" class="result__a" href="https://example.com/2">Result Two</a>
    <a class="result__snippet">This is snippet two</a>
    </body>
    </html>
    """
    results = SearchFallback._parse_html_results(html, 5)
    assert len(results) == 2
    assert results[0]["title"] == "Result One"
    assert results[0]["url"] == "https://example.com/1"
    assert results[1]["title"] == "Result Two"


@pytest.mark.asyncio
async def test_search_fallback_parse_html_max_results() -> None:
    """验证结果数量限制。"""
    html = """
    <html><body>
    <a rel="nofollow" class="result__a" href="https://example.com/1">R1</a>
    <a rel="nofollow" class="result__a" href="https://example.com/2">R2</a>
    <a rel="nofollow" class="result__a" href="https://example.com/3">R3</a>
    </body></html>
    """
    results = SearchFallback._parse_html_results(html, 2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_fallback_search_and_index_without_vector_store() -> None:
    """验证无向量存储时搜索和索引（降级跳过索引）。"""
    fallback = SearchFallback(llm_gateway=None)

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html><body>
        <a rel="nofollow" class="result__a" href="https://example.com">Test</a>
        <a class="result__snippet">Test snippet</a>
        </body></html>
        """
        mock_get.return_value = mock_resp

        results = await fallback.search_and_index(
            query="test",
            workspace_id="ws-1",
            max_results=5,
            vector_store=None,
        )

    assert len(results) > 0
