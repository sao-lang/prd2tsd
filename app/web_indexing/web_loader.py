"""Web 资源加载器 — 单次 URL 抓取 + Readability 正文提取。"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logger import get_logger

logger = get_logger("prd2tsd.web_loader")

# 简单 HTML 正文提取模式（不用 Readability 库，减少依赖）
_BODY_PATTERNS = [
    '<article[^>]*>',
    '<main[^>]*>',
    '<div[^>]*class="[^"]*content[^"]*"',
    '<div[^>]*class="[^"]*post[^"]*"',
    '<div[^>]*class="[^"]*article[^"]*"',
    '<body[^>]*>',
]

_USER_AGENT = (
    "Mozilla/5.0 (compatible; Prd2TsdBot/1.0; +https://prd2tsd.dev)"
)


class WebLoader:
    """Web 资源加载器。

    抓取 URL 内容，提取正文为 Markdown。
    """

    def __init__(self, timeout: int = 30) -> None:
        """初始化 Web 加载器。

        Args:
            timeout: 请求超时（秒）。
        """
        self.timeout = timeout

    async def fetch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """抓取 URL 并提取正文。

        Args:
            url: 目标 URL。
            headers: 自定义请求头。

        Returns:
            {
                "url": str,
                "title": str,
                "content": str,          # Markdown 格式正文
                "text_content": str,     # 纯文本正文
                "html": str,             # 原始 HTML
                "content_type": str,
                "status_code": int,
                "error": str | None,
            }
        """
        result: dict[str, Any] = {
            "url": url,
            "title": "",
            "content": "",
            "text_content": "",
            "html": "",
            "content_type": "",
            "status_code": 0,
            "error": None,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": _USER_AGENT,
                        **(headers or {}),
                    },
                )
                resp.raise_for_status()
                result["status_code"] = resp.status_code
                result["content_type"] = resp.headers.get("content-type", "")
                html = resp.text
                result["html"] = html

                # 提取标题
                title = self._extract_title(html)
                result["title"] = title

                # 提取正文
                text_content = self._extract_text(html)
                result["text_content"] = text_content

                # 转 Markdown
                md_content = self._html_to_markdown_simple(html, title)
                result["content"] = md_content

                logger.info(
                    "Web 页面已抓取: %s (%d bytes, title=%s)",
                    url, len(html), title[:50] if title else "N/A",
                )

        except httpx.TimeoutException as exc:
            result["error"] = f"请求超时: {exc}"
            logger.warning("URL 超时: %s", url)
        except httpx.HTTPStatusError as exc:
            result["error"] = f"HTTP 错误: {exc.response.status_code}"
            result["status_code"] = exc.response.status_code
            logger.warning("URL HTTP 错误: %s - %d", url, exc.response.status_code)
        except Exception as exc:
            result["error"] = f"抓取失败: {exc}"
            logger.warning("URL 抓取失败: %s - %s", url, exc)

        return result

    @staticmethod
    def _extract_title(html: str) -> str:
        """从 HTML 中提取标题。

        Args:
            html: HTML 源码。

        Returns:
            页面标题。
        """
        import re
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_text(html: str) -> str:
        """从 HTML 中提取纯文本。

        Args:
            html: HTML 源码。

        Returns:
            纯文本内容。
        """
        import re
        # 移除 script/style
        text = re.sub(r'<script[^>]*>.*?</script>', "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', "", text, flags=re.DOTALL | re.IGNORECASE)
        # 提取 body 内内容
        body_m = re.search(r'<body[^>]*>(.*)</body>', text, re.DOTALL | re.IGNORECASE)
        if body_m:
            text = body_m.group(1)
        # 去标签
        text = re.sub(r'<[^>]+>', " ", text)
        text = re.sub(r'\s+', " ", text).strip()
        return text[:10000]  # 限制长度

    @staticmethod
    def _html_to_markdown_simple(html: str, title: str) -> str:
        """简单 HTML 转 Markdown。

        Args:
            html: HTML 源码。
            title: 页面标题。

        Returns:
            Markdown 格式内容。
        """
        import re
        parts: list[str] = []
        if title:
            parts.append(f"# {title}")
            parts.append("")

        # 提取正文区域
        body = html
        for pattern in _BODY_PATTERNS:
            m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if m:
                start = html.find(m.group(0))
                if start >= 0:
                    body = html[start:]
                    # 找对应的结束标签
                    end_tag = m.group(0).split()[0].strip("<>")
                    end_m = re.search(fr'</{end_tag}>', body, re.IGNORECASE)
                    if end_m:
                        body = body[:end_m.end()]
                    break

        # 转换常用标签
        # h1-h6
        body = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', body, flags=re.DOTALL | re.IGNORECASE)
        # p / br
        body = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)
        # li
        body = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', body, flags=re.DOTALL | re.IGNORECASE)
        # strong / b
        body = re.sub(r'</?strong[^>]*>', '**', body, flags=re.IGNORECASE)
        body = re.sub(r'</?b[^>]*>', '**', body, flags=re.IGNORECASE)
        body = re.sub(r'</?em[^>]*>', '*', body, flags=re.IGNORECASE)
        body = re.sub(r'</?i[^>]*>', '*', body, flags=re.IGNORECASE)
        # a
        body = re.sub(
            r'<a[^>]*href=[\'"]([^\'"]*)[\'"][^>]*>(.*?)</a>',
            r'[\2](\1)',
            body, flags=re.DOTALL | re.IGNORECASE,
        )
        # code
        body = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', body, flags=re.DOTALL | re.IGNORECASE)
        # pre
        body = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n', body, flags=re.DOTALL | re.IGNORECASE)

        # 清理残留标签 + 多余空行
        body = re.sub(r'<[^>]+>', '', body)
        body = re.sub(r'\n{3,}', '\n\n', body)
        body = body.strip()

        parts.append(body)
        return "\n".join(parts)
