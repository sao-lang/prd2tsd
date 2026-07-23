"""TextUnit 构建 — Chunk 与 Entity 之间的桥梁层。"""

from __future__ import annotations

import uuid

from app.core.logger import get_logger
from app.knowledge_layer.models import Chunk, KGEntity, KGRelation, TextUnit

logger = get_logger("prd2tsd.knowledge.text_unit_builder")


class TextUnitBuilder:
    """TextUnit 构建器。

    将 Chunk 转换为 TextUnit，并关联实体和关系。
    """

    def build(
        self,
        chunks: list[Chunk],
        entities: list[KGEntity],
        relations: list[KGRelation],
        workspace_id: str = "",
    ) -> list[TextUnit]:
        """构建 TextUnit 列表。

        Args:
            chunks: 文档分块列表。
            entities: 实体列表。
            relations: 关系列表。
            workspace_id: 工作空间 ID。

        Returns:
            TextUnit 列表。
        """
        # 建立 entity_id -> entity 和 relation_id -> relation 映射
        entity_by_chunk: dict[str, list[str]] = {}
        for entity in entities:
            chunk_id = entity.source_text_unit_id or ""
            if chunk_id not in entity_by_chunk:
                entity_by_chunk[chunk_id] = []
            entity_by_chunk[chunk_id].append(entity.id)

        relation_by_chunk: dict[str, list[str]] = {}
        for relation in relations:
            chunk_id = relation.source_text_unit_id or ""
            if chunk_id not in relation_by_chunk:
                relation_by_chunk[chunk_id] = []
            relation_by_chunk[chunk_id].append(relation.id)

        text_units: list[TextUnit] = []
        for chunk in chunks:
            text_unit = TextUnit(
                id=str(uuid.uuid4()),
                text=chunk.text,
                entities=entity_by_chunk.get(chunk.id, []),
                relations=relation_by_chunk.get(chunk.id, []),
                section_path=chunk.section_path,
                chunk_index=chunk.index,
                workspace_id=workspace_id,
            )
            text_units.append(text_unit)

        logger.info("TextUnit 构建完成: %d units", len(text_units))
        return text_units
