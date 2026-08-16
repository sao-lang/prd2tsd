"""RAG 评测模块 — 检索质量（L1）+ 回答质量（L2），基于 deepeval。"""

from __future__ import annotations

from app.evaluation.rag.dataset_loader import load_rag_dataset
from app.evaluation.rag.evaluator import RagEvaluator
from app.evaluation.rag.models import (
    RagEvalReport,
    RagEvalSummary,
    RagQueryScore,
    RagSample,
)

__all__ = [
    "RagEvaluator",
    "RagEvalReport",
    "RagEvalSummary",
    "RagQueryScore",
    "RagSample",
    "load_rag_dataset",
]
