"""会话老化清理策略 — 按套餐保留期限自动清理过期会话。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.session_history.repository import SessionRepository

logger = get_logger("prd2tsd.session_cleanup")


class SessionCleanupPolicy:
    """会话老化清理策略。

    清理规则（基于套餐）：
    - Free:    30 天
    - Pro:    180 天
    - Enterprise: 不限（不清理）
    """

    RETENTION_DAYS: dict[str, int] = {
        "free": 30,
        "pro": 180,
        "enterprise": 0,  # 0 表示不限
    }

    def __init__(self, repository: SessionRepository | None = None) -> None:
        """初始化清理策略。

        Args:
            repository: 会话仓库。为 None 时自动创建。
        """
        self.repository = repository or SessionRepository()

    def get_retention_days(self, plan: str) -> int:
        """获取指定套餐的保留天数。

        Args:
            plan: 套餐名（free / pro / enterprise）。

        Returns:
            保留天数。0 表示不限。
        """
        return self.RETENTION_DAYS.get(plan.lower(), 30)

    async def cleanup(
        self,
        db: AsyncSession,
        workspace_id: str,
        plan: str = "free",
    ) -> int:
        """执行老化清理。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            plan: 工作空间套餐。

        Returns:
            清理的会话数。
        """
        retention_days = self.get_retention_days(plan)
        if retention_days <= 0:
            logger.info("工作空间 %s（%s）不限保留期，跳过清理", workspace_id, plan)
            return 0

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        deleted = await self.repository.cleanup_expired(db, workspace_id, cutoff)
        if deleted > 0:
            logger.info(
                "工作空间 %s 清理了 %d 个过期会话（> %d 天）",
                workspace_id, deleted, retention_days,
            )
        return deleted
