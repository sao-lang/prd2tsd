"""Claims/Covariates 提取 — 从 TextUnit 中提取声明性断言。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.llm import llm_complete
from app.core.logger import get_logger
from app.knowledge_layer.models import Claim, KGEntity, TextUnit

logger = get_logger("prd2tsd.knowledge.claims_extractor")

CLAIMS_PROMPT = """你是一个知识图谱声明性断言提取专家。从以下文本中提取声明性断言（Claims）。

Claim 类型包括：
- comparison: 对比（A 比 B 更好/更快等）
- decision: 决策（选择/采用某个技术）
- specification: 规格说明（版本号、配置参数等）
- constraint: 约束条件（必须/不能/限制等）
- prediction: 预测（预计效果、趋势等）

文本：
{text}

相关实体：
{entities_text}

请以 JSON 数组格式返回，每个 claim 包含：
{{
  "subject": "主语（实体名称）",
  "object": "宾语（可选，另一实体名称）",
  "claim_type": "claim 类型",
  "content": "断言内容（一段简明的陈述）",
  "confidence": 0.9
}}

只返回 JSON 数组，不要包含其他说明。"""


class ClaimsExtractor:
    """Claims/Covariates 提取器。"""

    def __init__(self, model: str | None = None) -> None:
        """初始化 Claims 提取器。

        Args:
            model: LLM 模型名。为 None 时使用默认模型。
        """
        self._model = model

    async def extract(
        self,
        text_units: list[TextUnit],
        entities: list[KGEntity],
    ) -> list[Claim]:
        """从 TextUnit 中提取 Claims。

        Args:
            text_units: TextUnit 列表。
            entities: 实体列表（用于关联 subject/object）。

        Returns:
            提取的 Claim 列表。
        """
        name_to_id = {e.name: e.id for e in entities}
        all_claims: list[Claim] = []

        for tu in text_units:
            claims = await self._extract_from_text_unit(tu, name_to_id)
            all_claims.extend(claims)

        logger.info("Claims 提取完成: %d claims", len(all_claims))
        return all_claims

    async def _extract_from_text_unit(
        self,
        text_unit: TextUnit,
        name_to_id: dict[str, str],
    ) -> list[Claim]:
        """从单个 TextUnit 提取 Claims。

        Args:
            text_unit: TextUnit。
            name_to_id: 实体名称到 ID 的映射。

        Returns:
            Claim 列表。
        """
        # 构建关联实体文本
        entity_names = list(text_unit.entities)
        entities_text = "\n".join(f"- {e_id}" for e_id in entity_names) if entity_names else "无"

        prompt = CLAIMS_PROMPT.format(
            text=text_unit.text[:2000],
            entities_text=entities_text,
        )

        try:
            response = await llm_complete(
                prompt=prompt,
                model=self._model,
                temperature=0.1,
                max_tokens=2048,
            )
            claims_data = self._parse_response(response)
        except Exception as e:
            logger.warning("Claims 提取失败: %s", str(e))
            return []

        claims: list[Claim] = []
        for data in claims_data:
            claims.append(
                Claim(
                    id=str(uuid.uuid4()),
                    subject=data.get("subject", ""),
                    subject_entity_id=name_to_id.get(data.get("subject", ""), ""),
                    object=data.get("object", ""),
                    object_entity_id=name_to_id.get(data.get("object", ""), ""),
                    claim_type=data.get("claim_type", "specification"),
                    content=data.get("content", ""),
                    confidence=float(data.get("confidence", 0.9)),
                    source_text_unit_id=text_unit.id,
                )
            )
        return claims

    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        """解析 LLM 返回的 JSON。

        Args:
            response: LLM 原始响应。

        Returns:
            Claim 数据列表。
        """
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            logger.warning("Claims 响应解析失败: %s...", response[:100])
            return []
