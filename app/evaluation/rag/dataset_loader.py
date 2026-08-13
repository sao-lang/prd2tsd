"""RAG 数据集加载。"""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.rag.models import RagSample


def load_rag_dataset(path: str | Path) -> list[RagSample]:
    """加载 RAG 黄金评测集。

    Args:
        path: rag_qa.json 路径。

    Returns:
        RagSample 列表。

    Raises:
        FileNotFoundError: 文件不存在。
        json.JSONDecodeError: JSON 解析失败。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = data.get("samples", [])
    return [RagSample(**sample) for sample in samples]
