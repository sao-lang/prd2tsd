"""集成生态 API 请求/响应体。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebhookRegisterRequest(BaseModel):
    """Webhook 注册请求。"""

    url: str = Field(..., description="回调 URL")
    event: str = Field(default="task.completed", description="事件类型")
    secret: str | None = Field(default=None, description="签名密钥")


class WebhookTestResponse(BaseModel):
    """Webhook 测试响应。"""

    success: bool
    status_code: int
    error: str | None = None


class WebFetchRequest(BaseModel):
    """Web 抓取请求。"""

    url: str = Field(..., description="目标 URL")


class WebFetchResult(BaseModel):
    """Web 抓取结果。"""

    url: str
    title: str = ""
    content: str = ""
    error: str | None = None


class CrawlRequest(BaseModel):
    """爬取请求。"""

    url: str = Field(..., description="起始 URL")
    max_pages: int = Field(default=20, ge=1, le=100)


class CrawlResult(BaseModel):
    """爬取结果。"""

    url: str
    title: str = ""
    content: str = ""
    error: str | None = None


class SearchFallbackResult(BaseModel):
    """搜索回退结果。"""

    query: str
    fallback_triggered: bool
    results: list[dict] = []
