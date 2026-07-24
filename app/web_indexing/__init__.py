"""Web 资源索引 — URL 抓取/递归爬虫/定时同步/搜索回退。"""

from app.web_indexing.search_fallback import SearchFallback
from app.web_indexing.web_crawler import WebCrawler
from app.web_indexing.web_loader import WebLoader
from app.web_indexing.web_sync import WebSyncScheduler

__all__ = [
    "WebLoader",
    "WebCrawler",
    "WebSyncScheduler",
    "SearchFallback",
]
