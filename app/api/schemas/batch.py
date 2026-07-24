"""批量任务 API 请求/响应体。"""

from pydantic import BaseModel


class BatchReindexRequest(BaseModel):
    """批量重索引请求。"""

    document_ids: list[str]


class BatchRegenerateRequest(BaseModel):
    """批量重新生成请求。"""

    prd_ids: list[str]


class TaskStatusResponse(BaseModel):
    """任务状态响应。"""

    id: str
    workspace_id: str
    type: str
    status: str
    progress: int = 0
    total: int = 0
    created_at: str | None = None
    finished_at: str | None = None
