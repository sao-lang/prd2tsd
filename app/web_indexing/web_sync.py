"""Web 定时同步 — ETag/Last-Modified/内容哈希变更检测。"""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from app.core.logger import get_logger

logger = get_logger("prd2tsd.web_sync")


class WebSyncScheduler:
    """Web 定时同步调度器。

    跟踪已同步的 URL，通过 ETag / Last-Modified / 内容哈希检测变更。
    """

    def __init__(self) -> None:
        """初始化同步调度器。"""
        # {url: {"etag": ..., "last_modified": ..., "content_hash": ...}}
        self._tracked: dict[str, dict[str, str]] = {}

    async def sync(
        self,
        url: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """同步单个 URL。

        Args:
            url: 目标 URL。
            force: 是否强制重新抓取（忽略缓存）。

        Returns:
            同步结果。{"changed": bool, "content": ..., "error": ...}
        """
        headers: dict[str, str] = {}
        prev = self._tracked.get(url, {})

        if not force:
            if prev.get("etag"):
                headers["If-None-Match"] = prev["etag"]
            elif prev.get("last_modified"):
                headers["If-Modified-Since"] = prev["last_modified"]

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; Prd2TsdBot/1.0)",
                        **headers,
                    },
                )

                if resp.status_code == 304:
                    logger.info("URL 未变更（304）: %s", url)
                    return {"changed": False, "url": url, "error": None}

                resp.raise_for_status()
                content = resp.text
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                # 对比内容哈希
                changed = prev.get("content_hash") != content_hash

                self._tracked[url] = {
                    "etag": resp.headers.get("etag", ""),
                    "last_modified": resp.headers.get("last-modified", ""),
                    "content_hash": content_hash,
                }

                logger.info(
                    "URL 同步完成: %s (changed=%s, size=%d)",
                    url, changed, len(content),
                )
                return {
                    "changed": changed,
                    "url": url,
                    "content": content,
                    "etag": resp.headers.get("etag", ""),
                    "last_modified": resp.headers.get("last-modified", ""),
                    "error": None,
                }

        except httpx.HTTPStatusError as exc:
            logger.warning("URL 同步失败: %s - %d", url, exc.response.status_code)
            return {"changed": False, "url": url, "error": f"HTTP {exc.response.status_code}"}
        except Exception as exc:
            logger.warning("URL 同步失败: %s - %s", url, exc)
            return {"changed": False, "url": url, "error": str(exc)}

    async def sync_multi(
        self,
        urls: list[str],
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """批量同步多个 URL。

        Args:
            urls: URL 列表。
            force: 是否强制。

        Returns:
            同步结果列表。
        """
        results: list[dict[str, Any]] = []
        for url in urls:
            result = await self.sync(url, force)
            results.append(result)
        return results

    def get_tracked_urls(self) -> list[str]:
        """获取所有已跟踪的 URL。

        Returns:
            URL 列表。
        """
        return list(self._tracked.keys())

    def clear(self) -> None:
        """清除跟踪状态。"""
        self._tracked.clear()
