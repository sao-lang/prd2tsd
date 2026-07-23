"""关系提取 — LLM 驱动的实体间关系提取。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.llm import llm_complete
from app.core.logger import get_logger
from app.knowledge_layer.models import Chunk, KGEntity, KGRelation

logger = get_logger("prd2tsd.knowledge.relation_extractor")

RELATION_PROMPT = """你是一个知识图谱关系提取专家。根据以下文本和实体列表，提取实体之间的关系。

实体列表：
{entities_text}

关系类型包括：
- depends_on: A 依赖于 B
- implements: A 实现 B
- recommends: A 推荐使用 B
- conflicts_with: A 与 B 冲突
- alternative_to: A 是 B 的替代方案
- part_of: A 是 B 的组成部分

文本：
{text}

请以 JSON 数组格式返回，每个关系包含：
{{
  "source": "源实体名称（必须与实体列表中的 name 一致）",
  "target": "目标实体名称",
  "type": "关系类型",
  "reason": "提取理由"
}}

只返回 JSON 数组，不要包含其他说明。"""


class RelationExtractor:
    """LLM 关系提取器。"""

    def __init__(self, model: str | None = None) -> None:
        """初始化关系提取器。

        Args:
            model: LLM 模型名。为 None 时使用默认模型。
        """
        self._model = model

    async def extract(
        self,
        entities: list[KGEntity],
        chunks: list[Chunk],
    ) -> list[KGRelation]:
        """从文档分块和实体中提取关系。

        Args:
            entities: 已提取的实体列表。
            chunks: 文档分块列表。

        Returns:
            提取的关系列表。
        """
        # 建立名称到 ID 的映射
        name_to_id = {e.name: e.id for e in entities}
        all_relations: list[KGRelation] = []
        processed_pairs: set[tuple[str, str, str]] = set()

        for chunk in chunks:
            relations = await self._extract_from_chunk(chunk, entities, name_to_id)
            for rel in relations:
                pair = (rel.source, rel.target, rel.type)
                if pair not in processed_pairs:
                    processed_pairs.add(pair)
                    all_relations.append(rel)

        logger.info("关系提取完成: %d relations", len(all_relations))
        return all_relations

    async def _extract_from_chunk(
        self,
        chunk: Chunk,
        entities: list[KGEntity],
        name_to_id: dict[str, str],
    ) -> list[KGRelation]:
        """从单个分块中提取关系。

        Args:
            chunk: 文档分块。
            entities: 实体列表。
            name_to_id: 名称到 ID 的映射。

        Returns:
            提取的关系列表。
        """
        # 只关联本 chunk 涉及的实体
        chunk_entity_names = [e.name for e in entities if e.source_text_unit_id == chunk.id]
        if not chunk_entity_names:
            return []

        entities_text = "\n".join(f"- {name}" for name in chunk_entity_names)
        prompt = RELATION_PROMPT.format(
            entities_text=entities_text,
            text=chunk.text[:3000],
        )

        try:
            response = await llm_complete(
                prompt=prompt,
                model=self._model,
                temperature=0.1,
                max_tokens=2048,
            )
            relations_data = self._parse_response(response)
        except Exception as e:
            logger.warning("关系提取失败 (chunk %d): %s", chunk.index, str(e))
            return []

        relations: list[KGRelation] = []
        for data in relations_data:
            source_name = data.get("source", "")
            target_name = data.get("target", "")
            source_id = name_to_id.get(source_name, "")
            target_id = name_to_id.get(target_name, "")
            if not source_id or not target_id:
                continue
            relations.append(
                KGRelation(
                    id=str(uuid.uuid4()),
                    source=source_id,
                    target=target_id,
                    type=data.get("type", "depends_on"),
                    reason=data.get("reason", ""),
                    source_text_unit_id=chunk.id,
                )
            )
        return relations

    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        """解析 LLM 返回的 JSON 响应。

        Args:
            response: LLM 原始响应。

        Returns:
            关系数据列表。
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
            logger.warning("关系提取响应解析失败: %s...", response[:100])
            return []
