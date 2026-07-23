"""数据脱敏引擎 — 自动检测替换 API Key/Token/密码等敏感信息。"""

from __future__ import annotations

import re
from typing import Any

from app.security.data_classifier import SENSITIVE_PATTERNS, DataClassifier, DataLevel


class DataMaskingEngine:
    """数据脱敏引擎。

    自动检测文本中的敏感信息（API Key、Token、密码、邮箱等）并替换为掩码标记。
    """

    def __init__(self) -> None:
        """初始化数据脱敏引擎。"""
        self._classifier = DataClassifier()
        self._patterns: dict[str, re.Pattern] = {}
        self._masks: dict[str, str] = {}

        for name, (pattern, _level) in SENSITIVE_PATTERNS.items():
            self._patterns[name] = re.compile(pattern, re.IGNORECASE)
            self._masks[name] = f"[MASKED_{name.upper()}]"

    def mask(self, text: str, level: str = "L2") -> str:
        """对文本进行脱敏处理。

        Args:
            text: 待脱敏的原始文本。
            level: 脱敏等级。L1 仅脱敏邮箱/IP；L2 额外脱敏密码/手机；
                   L3 额外脱敏 API Key/Token/证件号；L4 全部脱敏。

        Returns:
            脱敏后的文本。
        """
        if not text:
            return text

        result = text
        target_level = DataLevel(level)

        for name, (_, data_level) in SENSITIVE_PATTERNS.items():
            # 只脱敏当前等级及以下的数据
            if self._classifier._level_rank(data_level) <= self._classifier._level_rank(target_level):
                result = self._patterns[name].sub(self._masks[name], result)

        return result

    def mask_with_details(self, text: str, level: str = "L2") -> dict[str, Any]:
        """脱敏并返回脱敏详情。

        Args:
            text: 待脱敏的原始文本。
            level: 脱敏等级。

        Returns:
            {"masked_text": 脱敏后文本, "masked_types": [已脱敏的数据类型]}。
        """
        result = text
        masked_types: list[str] = []
        target_level = DataLevel(level)

        for name, (_, data_level) in SENSITIVE_PATTERNS.items():
            pattern = self._patterns[name]
            dl = self._classifier._level_rank(data_level)
            tl = self._classifier._level_rank(target_level)
            if pattern.search(result) and dl <= tl:
                masked_types.append(name)
                result = pattern.sub(self._masks[name], result)

        return {
            "masked_text": result,
            "masked_types": masked_types,
        }

    def get_classifier(self) -> DataClassifier:
        """获取数据分类器。

        Returns:
            DataClassifier 实例。
        """
        return self._classifier
