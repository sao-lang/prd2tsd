"""评测分数历史 — ScoreCalibrator 的持久化数据源（替代进程内 history）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.models.persistence import EvaluationScore

logger = get_logger("prd2tsd.evaluation.score_history")


async def load_recent_scores(limit: int = 10) -> list[dict[str, float]]:
    """加载最近 N 条评测总分（按时间倒序），用于历史比对校准。

    Args:
        limit: 返回条数。

    Returns:
        历史总分列表 [{"overall": float, ...dimensions}]；无数据库/空时返回 []。
    """
    try:
        pg = connection_manager.get("postgres")
        async with pg.get_session() as db:
            result = await db.execute(
                select(EvaluationScore)
                .order_by(EvaluationScore.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            history: list[dict[str, float]] = []
            for row in rows:
                item: dict[str, Any] = {"overall": float(row.overall_score or 0.0)}
                if row.dimension_scores:
                    item.update(
                        {k: float(v) for k, v in row.dimension_scores.items() if isinstance(v, (int, float))}
                    )
                history.append(item)
            return history
    except Exception as exc:
        logger.warning("加载评测历史失败（降级无历史）: %s", exc)
        return []


async def save_evaluation_score(
    workspace_id: str,
    task_id: str,
    overall_score: float,
    dimension_scores: dict[str, float],
) -> None:
    """持久化一次评测分数（失败不中断评分流程）。

    Args:
        workspace_id: 工作空间 ID。
        task_id: 任务 ID。
        overall_score: 总分。
        dimension_scores: 维度分数字典。
    """
    try:
        pg = connection_manager.get("postgres")
        async with pg.get_session() as db:
            db.add(
                EvaluationScore(
                    workspace_id=workspace_id or None,
                    task_id=task_id or None,
                    overall_score=overall_score,
                    dimension_scores=dimension_scores,
                    created_at=datetime.now(UTC),
                )
            )
            await db.commit()
    except Exception as exc:
        logger.warning("保存评测历史失败（不影响评分）: %s", exc)
