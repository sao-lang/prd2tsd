"""RRF 融合 — 多路检索结果的 Reciprocal Rank Fusion。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import ScoredDoc

logger = get_logger("prd2tsd.knowledge.fusion")


class RRFFusion:
    """RRF 融合器 — Reciprocal Rank Fusion。"""

    def __init__(self, k: int | None = None) -> None:
        """初始化 RRF 融合器。

        Args:
            k: RRF 常数（默认 60）。
        """
        self._k = k or kn_config.rrf_k

    def fuse(self, *ranked_lists: list[ScoredDoc]) -> list[ScoredDoc]:
        """融合多路排序结果。

        Args:
            *ranked_lists: 多个排序结果列表。

        Returns:
            融合后的排序结果。
        """
        score_map: dict[str, ScoredDoc] = {}
        total_lists = sum(1 for lst in ranked_lists if lst)

        for ranked_list in ranked_lists:
            for rank, doc in enumerate(ranked_list):
                if doc.id not in score_map:
                    score_map[doc.id] = doc.model_copy()
                    score_map[doc.id].score = 0.0

                # RRF 分数累加
                score_map[doc.id].score += 1.0 / (self._k + rank + 1)

        # 归一化
        if total_lists > 0:
            for doc in score_map.values():
                doc.score = doc.score / total_lists

        # 按分数排序
        sorted_docs = sorted(score_map.values(), key=lambda d: d.score, reverse=True)

        logger.debug("RRF 融合完成: %d inputs -> %d results", total_lists, len(sorted_docs))
        return sorted_docs
