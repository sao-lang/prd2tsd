"""RAG 评测模块 — 检索质量（L1）+ 回答质量（L2），基于 ragas。"""

from __future__ import annotations

from app.evaluation.rag._compat import install_ragas_shims
from app.evaluation.rag.dataset_loader import load_rag_dataset
from app.evaluation.rag.evaluator import RagEvaluator
from app.evaluation.rag.models import (
    RagEvalReport,
    RagEvalSummary,
    RagQueryScore,
    RagSample,
)

# 评测模块导入即安装 ragas 兼容 shim
install_ragas_shims()

__all__ = [
    "RagEvaluator",
    "RagEvalReport",
    "RagEvalSummary",
    "RagQueryScore",
    "RagSample",
    "load_rag_dataset",
]
