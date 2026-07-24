"""CSV 双通路索引 — 行级 TextUnit + 列级 Embedding。"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.csv_indexer")


class CsvDualPathIndexer:
    """CSV/TSV 双通路索引器。

    构建两种索引：
    1. 行级 TextUnit：每行 → 自然语言句子
    2. 列级 Embedding：列名+列描述 → 语义向量
    3. 列类型自动推断
    4. 外键自动检测（_id/_key 后缀启发）
    """

    # 正则模式：列名以 _id 或 _key 结尾
    FK_PATTERN = re.compile(r"_(id|key)$", re.IGNORECASE)

    async def process(
        self,
        content: bytes,
        filename: str,
        document_id: str,
    ) -> dict[str, Any]:
        """处理 CSV/TSV 文件，构建双通路索引。

        Args:
            content: 文件字节数据。
            filename: 文件名。
            document_id: 文档 ID。

        Returns:
            索引结果：{
                "text_units": list[str],
                "column_profiles": list[dict],
                "row_count": int,
                "column_count": int,
            }
        """
        delimiter = self._detect_delimiter(filename)
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)

        if not rows:
            return {
                "text_units": [],
                "column_profiles": [],
                "row_count": 0,
                "column_count": 0,
            }

        fieldnames = reader.fieldnames or []
        column_count = len(fieldnames)

        # 列级分析
        column_profiles = self._analyze_columns(fieldnames, rows)

        # 外键检测
        foreign_keys = self._detect_foreign_keys(fieldnames)
        for profile in column_profiles:
            if profile["name"] in foreign_keys:
                profile["is_foreign_key"] = True

        # 行级 TextUnit
        text_units = self._build_text_units(fieldnames, rows, filename)

        logger.info(
            "CSV 索引完成: %d 行, %d 列, %d 外键, %d text_units",
            len(rows), column_count, len(foreign_keys), len(text_units),
        )

        return {
            "text_units": text_units,
            "column_profiles": column_profiles,
            "row_count": len(rows),
            "column_count": column_count,
            "foreign_keys": foreign_keys,
        }

    @staticmethod
    def _detect_delimiter(filename: str) -> str:
        """检测分隔符。

        Args:
            filename: 文件名。

        Returns:
            分隔符（逗号或制表符）。
        """
        if filename.lower().endswith(".tsv"):
            return "\t"
        return ","

    @staticmethod
    def _analyze_columns(
        fieldnames: list[str],
        rows: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """分析列信息。

        Args:
            fieldnames: 列名列表。
            rows: 数据行。

        Returns:
            列分析结果列表。
        """
        profiles: list[dict[str, Any]] = []
        for col in fieldnames:
            values = [row.get(col, "") for row in rows if col in row]
            non_empty = [v for v in values if v.strip()]

            col_type = _infer_column_type(non_empty)
            profiles.append({
                "name": col,
                "type": col_type,
                "non_null_count": len(non_empty),
                "total_count": len(values),
                "sample_values": non_empty[:5],
                "is_foreign_key": False,
            })
        return profiles

    @staticmethod
    def _detect_foreign_keys(fieldnames: list[str]) -> list[str]:
        """检测外键列。

        Args:
            fieldnames: 列名列表。

        Returns:
            被检测为外键的列名列表。
        """
        return [col for col in fieldnames if CsvDualPathIndexer.FK_PATTERN.search(col)]

    @staticmethod
    def _build_text_units(
        fieldnames: list[str],
        rows: list[dict[str, str]],
        filename: str,
    ) -> list[str]:
        """构建行级 TextUnit（每行 → 自然语言句子）。

        Args:
            fieldnames: 列名列表。
            rows: 数据行。
            filename: 文件名。

        Returns:
            TextUnit 列表。
        """
        units: list[str] = []
        for i, row in enumerate(rows):
            parts: list[str] = []
            for col in fieldnames:
                val = row.get(col, "").strip()
                if val:
                    parts.append(f"{col} 为 {val}")
            if parts:
                sentence = f"在文件 {filename} 的第 {i + 2} 行：{'，'.join(parts)}。"
                units.append(sentence)
        return units


def _infer_column_type(values: list[str]) -> str:
    """推断列类型。

    Args:
        values: 该列的非空值列表。

    Returns:
        推断的类型名。
    """
    if not values:
        return "string"

    # 尝试解析为 integer
    all_int = all(_is_int(v) for v in values)
    if all_int:
        return "integer"

    # 尝试解析为 float
    all_float = all(_is_float(v) for v in values)
    if all_float:
        return "float"

    # 尝试检测日期
    date_count = sum(1 for v in values if _is_date(v))
    if date_count > len(values) * 0.8:
        return "date"

    # 检测枚举（唯一值少于总值的 10%，且样本数足够时）
    unique = set(values)
    if len(values) >= 10 and len(unique) <= max(3, len(values) * 0.1):
        return "enum"

    return "string"


def _is_int(v: str) -> bool:
    """判断是否为整数。"""
    try:
        int(v)
        return True
    except (ValueError, TypeError):
        return False


def _is_float(v: str) -> bool:
    """判断是否为浮点数。"""
    try:
        float(v)
        return "." in v
    except (ValueError, TypeError):
        return False


_DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),
    re.compile(r"^\d{4}\.\d{2}\.\d{2}$"),
]


def _is_date(v: str) -> bool:
    """判断是否为日期格式。"""
    return any(p.match(v) for p in _DATE_PATTERNS)
