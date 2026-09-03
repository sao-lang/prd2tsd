"""基于已提取实体生成可验证的知识图谱关系。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.ingestion.entity_resolver import EntityResolver
from app.knowledge_layer.models import Chunk, KGEntity, KGRelation
from app.llm_gateway import gateway

logger = get_logger("prd2tsd.knowledge.relation_extractor")

RELATION_EXTRACTION_PROMPT = """你是知识图谱关系抽取器。只根据给定文本和候选实体抽取明确关系。

候选实体：
{entities}

文本：
{text}

返回 JSON 数组，每项格式：
{{
  "source": "候选实体中的源实体名称",
  "target": "候选实体中的目标实体名称",
  "relation_type": "简短关系类型，例如 uses/depends_on/stores_in/implements/constrained_by",
  "description": "关系依据的简短描述",
  "confidence": 0.0
}}

要求：source 和 target 必须来自候选实体，禁止创造实体；没有明确关系时返回 []；只返回 JSON 数组。"""


class RelationExtractor:
    """逐 Chunk 抽取关系，并把关系端点绑定到消歧后的实体 ID。"""

    def __init__(self, model: str | None = None, resolver: EntityResolver | None = None) -> None:
        self._model = model
        self._resolver = resolver or EntityResolver()

    async def extract(
        self,
        chunks: list[Chunk],
        source_entities: list[KGEntity],
        resolved_entities: list[KGEntity],
        workspace_id: str = "",
    ) -> list[KGRelation]:
        """抽取并验证关系。

        Args:
            chunks: 原文分块。
            source_entities: 本轮实体抽取结果，用于限定每个 Chunk 的候选名称。
            resolved_entities: 消歧后的实体，用于解析稳定端点 ID。
            workspace_id: 工作空间 ID。

        Returns:
            端点有效且去重后的关系列表。
        """
        relations_by_id: dict[str, KGRelation] = {}
        entities_by_chunk: dict[str, list[KGEntity]] = {}
        for entity in source_entities:
            entities_by_chunk.setdefault(entity.source_text_unit_id, []).append(entity)

        for chunk in chunks:
            candidates = entities_by_chunk.get(chunk.id, [])
            if len(candidates) < 2:
                continue
            for relation in await self._extract_from_chunk(
                chunk,
                candidates,
                resolved_entities,
                workspace_id,
            ):
                current = relations_by_id.get(relation.id)
                if current is None or relation.confidence > current.confidence:
                    relations_by_id[relation.id] = relation

        relations = list(relations_by_id.values())
        logger.info("关系提取完成: %d relations", len(relations))
        return relations

    async def _extract_from_chunk(
        self,
        chunk: Chunk,
        candidates: list[KGEntity],
        resolved_entities: list[KGEntity],
        workspace_id: str,
    ) -> list[KGRelation]:
        """从单个 Chunk 抽取关系并验证端点。"""
        entity_names = [entity.name for entity in candidates[:80]]
        prompt = RELATION_EXTRACTION_PROMPT.format(
            entities=json.dumps(entity_names, ensure_ascii=False),
            text=chunk.text[:2000],
        )
        try:
            response = await gateway.complete(
                prompt=prompt,
                task_type="default",
                workspace_id=workspace_id,
                layer="knowledge",
                node="relation_extractor",
                model=self._model,
                temperature=0.1,
                max_tokens=2048,
            )
            if response.metadata.get("error") or response.metadata.get("blocked"):
                logger.warning("关系抽取被 Gateway 拒绝: chunk=%d metadata=%s", chunk.index, response.metadata)
                return []
            data = self._parse_response(response.content)
        except Exception as exc:
            logger.warning("关系抽取失败 (chunk %d): %s", chunk.index, exc)
            return []

        candidate_names = {entity.name.casefold() for entity in candidates}
        relations: list[KGRelation] = []
        for item in data:
            source_name = str(item.get("source", "")).strip()
            target_name = str(item.get("target", "")).strip()
            if source_name.casefold() not in candidate_names or target_name.casefold() not in candidate_names:
                continue
            source = self._resolver.find_by_name(source_name, resolved_entities)
            target = self._resolver.find_by_name(target_name, resolved_entities)
            if source is None or target is None or not source.id or not target.id or source.id == target.id:
                continue
            relation_type = self._normalise_relation_type(str(item.get("relation_type", "related_to")))
            relation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{workspace_id}:{source.id}:{relation_type}:{target.id}"))
            try:
                confidence = min(1.0, max(0.0, float(item.get("confidence", 0.8))))
            except (TypeError, ValueError):
                confidence = 0.8
            relations.append(
                KGRelation(
                    id=relation_id,
                    source_entity_id=source.id,
                    target_entity_id=target.id,
                    relation_type=relation_type,
                    description=str(item.get("description", "")).strip()[:1000],
                    confidence=confidence,
                    source_text_unit_id=chunk.id,
                    workspace_id=workspace_id,
                )
            )
        return relations

    @staticmethod
    def _normalise_relation_type(value: str) -> str:
        """把模型关系类型收敛为可查询的安全标识。"""
        normalised = re.sub(r"[^a-z0-9_]+", "_", value.casefold().strip()).strip("_")
        return normalised[:64] or "related_to"

    @staticmethod
    def _parse_response(response: str) -> list[dict[str, Any]]:
        """解析可能带 Markdown 围栏的关系 JSON。"""
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError:
            return []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
