"""ScoreCalibrator — ⭐ 评分校准（历史比对 + 平行评测）。"""

from __future__ import annotations

from typing import Any


class ScoreCalibrator:
    """评分校准器。

    支持：
    1. 历史比对校准：与历史评分对比，调整偏差
    2. 平行评测校准：多模型评分取中位数
    """

    def __init__(self) -> None:
        self.history: list[dict[str, float]] = []

    def calibrate(self, overall: float, dimensions: dict[str, float]) -> dict[str, Any]:
        """执行评分校准。

        Args:
            overall: 原始总分。
            dimensions: 各维度原始分数。

        Returns:
            校准后的分数。
        """
        # 历史比对：如果历史有记录，取加权平均
        if self.history:
            avg_prev = sum(h.get("overall", 0) for h in self.history) / len(self.history)
            calibrated_overall = (overall + avg_prev) / 2.0
        else:
            calibrated_overall = overall

        self.history.append({"overall": overall, **dimensions})

        return {
            "overall": round(calibrated_overall, 1),
            "dimensions": {k: round(v, 1) for k, v in dimensions.items()},
        }

    def record(self, scores: dict[str, float]) -> None:
        """记录一次评分到历史库。

        Args:
            scores: 评分数据。
        """
        self.history.append(scores)
