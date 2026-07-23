"""Re-ranker — Cross-encoder 重排。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.models import ScoredDoc

logger = get_logger("prd2tsd.knowledge.reranker")


class ReRanker:
    """Cross-encoder 重排器。

    使用 HuggingFace Cross-encoder 模型对检索结果重排。
    默认使用 BAAI/bge-reranker-v2-m3（轻量级多语言重排模型）。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        """初始化重排器。

        Args:
            model_name: Cross-encoder 模型名。
        """
        self._model_name = model_name
        self._model: Any = None
        self._tokenizer: Any = None

    def _lazy_load(self) -> None:
        """延迟加载模型。"""
        if self._model is None:
            try:
                from transformers import AutoModelForSequenceClassification, AutoTokenizer

                self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
                self._model = AutoModelForSequenceClassification.from_pretrained(self._model_name)
                logger.info("重排模型已加载: %s", self._model_name)
            except Exception as e:
                logger.warning("重排模型加载失败，使用简单重排: %s", str(e))

    def rerank(self, query: str, candidates: list[ScoredDoc], top_k: int = 10) -> list[ScoredDoc]:
        """对候选结果重排。

        Args:
            query: 查询文本。
            candidates: 候选结果列表。
            top_k: 返回结果数。

        Returns:
            重排后的结果列表。
        """
        if not candidates:
            return []

        self._lazy_load()

        if self._model is not None and self._tokenizer is not None:
            return self._cross_encoder_rerank(query, candidates, top_k)

        return self._simple_rerank(query, candidates, top_k)

    def _cross_encoder_rerank(
        self,
        query: str,
        candidates: list[ScoredDoc],
        top_k: int,
    ) -> list[ScoredDoc]:
        """使用 Cross-encoder 重排。

        Args:
            query: 查询文本。
            candidates: 候选结果。
            top_k: 返回数量。

        Returns:
            重排后的结果。
        """
        import torch

        pairs = [(query, doc.text[:512]) for doc in candidates]
        inputs = self._tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )

        with torch.no_grad():
            outputs = self._model(**inputs)
            scores = outputs.logits.squeeze(-1).tolist()

        if isinstance(scores, float):
            scores = [scores]

        for doc, score in zip(candidates, scores, strict=False):
            doc.score = float(score)

        reranked = sorted(candidates, key=lambda d: d.score, reverse=True)
        logger.debug("Cross-encoder 重排完成: %d -> %d", len(candidates), len(reranked[:top_k]))
        return reranked[:top_k]

    def _simple_rerank(
        self,
        query: str,
        candidates: list[ScoredDoc],
        top_k: int,
    ) -> list[ScoredDoc]:
        """无模型时的简单重排（基于关键词覆盖）。

        Args:
            query: 查询文本。
            candidates: 候选结果。
            top_k: 返回数量。

        Returns:
            重排后的结果。
        """
        query_tokens = set(query.lower().split())
        if not query_tokens:
            return candidates[:top_k]

        for doc in candidates:
            doc_tokens = set(doc.text.lower().split())
            overlap = len(query_tokens & doc_tokens)
            coverage = overlap / len(query_tokens) if query_tokens else 0
            # 原始分数 + 关键词覆盖加权
            doc.score = doc.score * 0.7 + coverage * 0.3

        reranked = sorted(candidates, key=lambda d: d.score, reverse=True)
        return reranked[:top_k]
