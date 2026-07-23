"""数据分类分级（L1-L4 标签）。"""

from __future__ import annotations

from enum import StrEnum


class DataLevel(StrEnum):
    """数据安全等级。

    L1: 公开 — 无需特殊处理
    L2: 内部 — 需要脱敏敏感信息
    L3: 敏感 — 严格脱敏，需审计
    L4: 机密 — 最高安全要求，脱敏+审计+加密
    """

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


# 敏感数据模式 → 安全等级
SENSITIVE_PATTERNS: dict[str, tuple[str, DataLevel]] = {
    "api_key": (r"(?i)(sk-|pk-|coh-)[a-z0-9]{8,}", DataLevel.L3),
    "password": (r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+", DataLevel.L2),
    "token": (r"(?i)(token|jwt|bearer)\s+\S+", DataLevel.L3),
    "email": (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", DataLevel.L1),
    "phone": (r"1[3-9]\d{9}", DataLevel.L2),
    "id_card": (r"\d{18}[\dXx]", DataLevel.L3),
    "ip_address": (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", DataLevel.L1),
}


class DataClassifier:
    """数据分类分级器。

    检测文本中的敏感数据类型，并返回对应的安全等级。
    """

    def __init__(self) -> None:
        """初始化数据分类分级器。"""
        import re

        self._patterns = {
            name: re.compile(pattern)
            for name, (pattern, _) in SENSITIVE_PATTERNS.items()
        }

    def classify(self, text: str) -> DataLevel:
        """对文本进行安全等级分类。

        Args:
            text: 待分类的文本。

        Returns:
            文本的安全等级（取最高等级）。
        """
        if not text:
            return DataLevel.L1

        max_level = DataLevel.L1
        for name, (_, level) in SENSITIVE_PATTERNS.items():
            pattern = self._patterns[name]
            if pattern.search(text) and self._level_rank(level) > self._level_rank(max_level):
                max_level = level

        return max_level

    def detect_sensitive_types(self, text: str) -> list[str]:
        """检测文本中包含的敏感数据类型。

        Args:
            text: 待检测的文本。

        Returns:
            敏感数据类型名称列表。
        """
        detected: list[str] = []
        for name in self._patterns:
            if self._patterns[name].search(text):
                detected.append(name)
        return detected

    @staticmethod
    def _level_rank(level: DataLevel) -> int:
        """获取安全等级的数值排名。

        Args:
            level: 安全等级。

        Returns:
            数值排名（L1=1, L4=4）。
        """
        return {"L1": 1, "L2": 2, "L3": 3, "L4": 4}.get(level.value, 1)
