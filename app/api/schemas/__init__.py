"""API Schemas。"""

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

from app.api.schemas.document import (
    CsvImportResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatsResponse,
    PreviewResponse,
    UploadResponse as DocumentUploadResponse,
)
from app.api.schemas.session import (
    ExportResponse,
    MessageCreateRequest,
    MessageResponse,
    PageResultResponse,
    SearchResultItem as SessionSearchResultItem,
    SessionCreateRequest,
    SessionResponse,
    SessionUpdateRequest,
)

from app.api.schemas.batch import (
    BatchReindexRequest,
    BatchRegenerateRequest,
    TaskStatusResponse,
)
from app.api.schemas.collaboration import (
    ChangeLogEntry,
    CommentCreateRequest,
    CommentResponse,
    SuggestionCreateRequest,
    SuggestionResponse,
)
from app.api.schemas.integration import (
    CrawlRequest,
    CrawlResult,
    SearchFallbackResult,
    WebFetchRequest,
    WebFetchResult,
    WebhookRegisterRequest,
    WebhookTestResponse,
)
from app.api.schemas.model_config import (
    ModelConfigResponse,
    ModelConfigUpdateRequest,
    RoutingRuleUpdateRequest,
)
from app.api.schemas.multimodal import (
    ImageIndexResponse,
    ImageSearchResult,
    SearchResultList,
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
    "CsvImportResponse",
    # batch
    "BatchReindexRequest",
    "BatchRegenerateRequest",
    "TaskStatusResponse",
    # collaboration
    "CommentCreateRequest",
    "CommentResponse",
    "SuggestionCreateRequest",
    "SuggestionResponse",
    "ChangeLogEntry",
    # integration
    "WebhookRegisterRequest",
    "WebhookTestResponse",
    "WebFetchRequest",
    "WebFetchResult",
    "CrawlRequest",
    "CrawlResult",
    "SearchFallbackResult",
    # model_config
    "ModelConfigResponse",
    "ModelConfigUpdateRequest",
    "RoutingRuleUpdateRequest",
    # multimodal
    "ImageSearchResult",
    "ImageIndexResponse",
    "SearchResultList",
]
