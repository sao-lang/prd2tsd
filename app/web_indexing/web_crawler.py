"""Web 爬虫 — 同域递归爬虫 + BFS + robots.txt 遵守。"""

from __future__ import annotations

import re
from collections import deque
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.logger import get_logger

logger = get_logger("prd2tsd.web_crawler")


class WebCrawler:
    """同域递归爬虫。

    基于 BFS 策略，遵守 robots.txt，支持并发控制。
    """

    def __init__(
        self,
        max_pages: int = 50,
        max_concurrency: int = 3,
        respect_robots: bool = True,
        allowed_paths: list[str] | None = None,
    ) -> None:
        """初始化爬虫。

        Args:
            max_pages: 最大抓取页数。
            max_concurrency: 最大并发数。
            respect_robots: 是否遵守 robots.txt。
            allowed_paths: 允许爬取的路径前缀。
        """
        self.max_pages = max_pages
        self.max_concurrency = max_concurrency
        self.respect_robots = respect_robots
        self.allowed_paths = allowed_paths

    async def crawl(
        self,
        start_url: str,
    ) -> list[dict[str, Any]]:
        """从起始 URL 开始爬取。

        Args:
            start_url: 起始 URL。

        Returns:
            抓取结果列表，每项包含 url / title / content / error。
        """
        parsed = urlparse(start_url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"
        visited: set[str] = set()
        queue: deque[str] = deque([start_url])
        results: list[dict[str, Any]] = []

        # 获取 robots.txt
        disallowed: list[str] = []
        if self.respect_robots:
            disallowed = await self._fetch_robots(base_domain)

        from app.web_indexing.web_loader import WebLoader
        loader = WebLoader()

        while queue and len(visited) < self.max_pages:
            url = queue.popleft()
            if url in visited:
                continue

            # robots.txt 检查
            if self._is_disallowed(url, disallowed, base_domain):
                visited.add(url)
                continue

            # 路径过滤
            if self.allowed_paths:
                path = urlparse(url).path
                if not any(path.startswith(p) for p in self.allowed_paths):
                    continue

            visited.add(url)
            fetch_result = await loader.fetch(url)
            results.append(fetch_result)

            if not fetch_result.get("error") and fetch_result.get("html"):
                links = self._extract_links(fetch_result["html"], base_domain)
                for link in links:
                    if link not in visited and link not in queue:
                        queue.append(link)

            logger.info(
                "爬虫进度: %d/%d, 队列: %d",
                len(visited), self.max_pages, len(queue),
            )

        logger.info(
            "爬虫完成: %s → %d 页 (成功 %d, 失败 %d)",
            start_url, len(results),
            sum(1 for r in results if not r.get("error")),
            sum(1 for r in results if r.get("error")),
        )
        return results

    @staticmethod
    async def _fetch_robots(base_domain: str) -> list[str]:
        """获取并解析 robots.txt。

        Args:
            base_domain: 基础域名。

        Returns:
            禁止爬取的路径列表。
        """
        disallowed: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base_domain}/robots.txt")
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        if line.lower().startswith("disallow:"):
                            path = line.split(":", 1)[1].strip()
                            if path:
                                disallowed.append(path)
        except Exception:
            pass
        return disallowed

    @staticmethod
    def _is_disallowed(
        url: str,
        disallowed: list[str],
        base_domain: str,
    ) -> bool:
        """检查 URL 是否被 robots.txt 禁止。

        Args:
            url: 待检查 URL。
            disallowed: 禁止路径列表。
            base_domain: 基础域名。

        Returns:
            是否被禁止。
        """
        if not disallowed:
            return False
        path = urlparse(url).path
        return any(path.startswith(d) for d in disallowed)

    @staticmethod
    def _extract_links(html: str, base_domain: str) -> set[str]:
        """从 HTML 中提取同域链接。

        Args:
            html: HTML 源码。
            base_domain: 基础域名。

        Returns:
            同域链接集合。
        """
        links: set[str] = set()
        for m in re.finditer(
            r'<a[^>]*href="([^"]*)"',
            html,
            re.IGNORECASE,
        ):
            href = m.group(1).strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            full_url = urljoin(base_domain, href)
            # 仅同域
            if urlparse(full_url).netloc == urlparse(base_domain).netloc:
                # 去 fragment
                clean = full_url.split("#")[0]
                if clean:
                    links.add(clean)
        return links
