"""多模态 API 请求/响应体。"""

from pydantic import BaseModel


class ImageSearchResult(BaseModel):
    """图片搜索结果。"""

    chunk_id: str
    document_id: str
    page_number: int
    caption: str = ""
    score: float = 0.0
    match_type: str = "visual"


class ImageIndexResponse(BaseModel):
    """图片索引响应。"""

    chunk_id: str
    document_id: str
    caption: str = ""


class SearchResultList(BaseModel):
    """搜索结果列表。"""

    results: list[ImageSearchResult]
    query_type: str = ""
