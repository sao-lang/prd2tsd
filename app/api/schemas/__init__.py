"""API Schemas。"""

from app.api.schemas.batch import (
    BatchRegenerateRequest,
    BatchReindexRequest,
    TaskStatusResponse,
)
from app.api.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatsResponse,
    PreviewResponse,
)
from app.api.schemas.document import (
    UploadResponse as DocumentUploadResponse,
)
from app.api.schemas.integration import (
    CrawlRequest,
    CrawlResult,
    WebFetchRequest,
    WebFetchResult,
    WebhookRegisterRequest,
    WebhookTestResponse,
)
from app.api.schemas.interact import (
    InteractRequest,
    InteractResponse,
)
from app.api.schemas.model_config import (
    ModelConfigResponse,
    ModelConfigUpdateRequest,
    RoutingRuleUpdateRequest,
)
from app.api.schemas.request import (
    LoginRequest,
    MemberAddRequest,
    RefreshTokenRequest,
    RegisterRequest,
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
)
from app.api.schemas.response import (
    HealthResponse,
    TokenResponse,
    UserInfoResponse,
    WorkspaceResponse,
)
from app.api.schemas.session import (
    ExportResponse,
    MessageCreateRequest,
    MessageResponse,
    PageResultResponse,
    SessionCreateRequest,
    SessionResponse,
    SessionUpdateRequest,
)
from app.api.schemas.session import (
    SearchResultItem as SessionSearchResultItem,
)
from app.api.schemas.streaming import (
    StreamReviewRequest,
)

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "RefreshTokenRequest",
    "WorkspaceCreateRequest",
    "WorkspaceUpdateRequest",
    "MemberAddRequest",
    "TokenResponse",
    "UserInfoResponse",
    "HealthResponse",
    "WorkspaceResponse",
    "SessionCreateRequest",
    "SessionUpdateRequest",
    "SessionResponse",
    "MessageCreateRequest",
    "MessageResponse",
    "PageResultResponse",
    "SessionSearchResultItem",
    "ExportResponse",
    "DocumentResponse",
    "DocumentListResponse",
    "DocumentStatsResponse",
    "DocumentUploadResponse",
    "PreviewResponse",
    # interact
    "InteractRequest",
    "InteractResponse",
    # batch
    "BatchReindexRequest",
    "BatchRegenerateRequest",
    "TaskStatusResponse",
    # integration
    "WebhookRegisterRequest",
    "WebhookTestResponse",
    "WebFetchRequest",
    "WebFetchResult",
    "CrawlRequest",
    "CrawlResult",
    # model_config
    "ModelConfigResponse",
    "ModelConfigUpdateRequest",
    "RoutingRuleUpdateRequest",
    # streaming
    "StreamReviewRequest",
]
