"""协作文档 — 行内评论 / 建议修改 / 变更历史。"""

from app.collaboration.changelog import ChangeLogService
from app.collaboration.comment import CommentService
from app.collaboration.service import CollaborationService
from app.collaboration.suggestion import SuggestionService

__all__ = [
    "CommentService",
    "SuggestionService",
    "ChangeLogService",
    "CollaborationService",
]
