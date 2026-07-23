"""实体提取 — LLM 驱动的技术实体提取。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.llm import llm_complete
from app.core.logger import get_logger
from app.knowledge_layer.models import Chunk, KGEntity

logger = get_logger("prd2tsd.knowledge.entity_extractor")

EXTRACTION_PROMPT = """你是一个知识图谱实体提取专家。从以下文本中提取技术相关的实体。

实体类型包括：
- TechStack: 技术栈（框架、语言、工具、库等）
- Component: 系统组件（模块、服务、功能模块等）
- ArchitecturePattern: 架构模式（设计模式、架构风格等）
- Constraint: 约束条件（技术约束、业务约束等）
- Concept: 概念（抽象概念、术语等）

请以 JSON 数组格式返回，每个实体包含：
{{
  "name": "实体名称",
  "type": "实体类型（必须是上面列出的类型之一）",
  "category": "分类（如"数据库"、"框架"、"协议"等）",
  "description": "实体描述"
}}

文本：
{text}

只返回 JSON 数组，不要包含其他说明。"""


class EntityExtractor:
    """LLM 实体提取器。"""

    def __init__(self, model: str | None = None) -> None:
        """初始化实体提取器。

        Args:
            model: LLM 模型名。为 None 时使用默认模型。
        """
        self._model = model

    async def extract(self, chunks: list[Chunk]) -> list[KGEntity]:
        """从分块中提取实体。

        Args:
            chunks: 文档分块列表。

        Returns:
            提取的实体列表。
        """
        all_entities: list[KGEntity] = []
        for chunk in chunks:
            entities = await self._extract_from_chunk(chunk)
            all_entities.extend(entities)
        logger.info("实体提取完成: %d entities", len(all_entities))
        return all_entities

    async def _extract_from_chunk(self, chunk: Chunk) -> list[KGEntity]:
        """从单个分块中提取实体。

        Args:
            chunk: 文档分块。

        Returns:
            提取的实体列表。
        """
        prompt = EXTRACTION_PROMPT.format(text=chunk.text[:2000])
        try:
            response = await llm_complete(
                prompt=prompt,
                model=self._model,
                temperature=0.1,
                max_tokens=2048,
            )
            entities_data = self._parse_response(response)
        except Exception as e:
            logger.warning("实体提取失败 (chunk %d): %s", chunk.index, str(e))
            return []

        entities: list[KGEntity] = []
        for data in entities_data:
            entity = KGEntity(
                id=str(uuid.uuid4()),
                name=data.get("name", ""),
                type=data.get("type", "Concept"),
                category=data.get("category", ""),
                description=data.get("description", ""),
                source_text_unit_id=chunk.id,
            )
            if entity.name:
                entities.append(entity)
        return entities

    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        """解析 LLM 返回的 JSON 响应。

        Args:
            response: LLM 原始响应。

        Returns:
            实体数据列表。
        """
        # 尝试提取 JSON 块
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
            logger.warning("实体提取响应解析失败: %s...", response[:100])
            return []
