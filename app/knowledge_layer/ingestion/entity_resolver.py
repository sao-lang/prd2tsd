"""实体融合/消歧 — 精确匹配 → 别名匹配 → 语义相似度 → 人工确认四级策略。"""

from __future__ import annotations

import hashlib

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import KGEntity, ResolutionAction

logger = get_logger("prd2tsd.knowledge.entity_resolver")

# 常见技术别名映射
ALIAS_MAP: dict[str, list[str]] = {
    "spring boot": ["spring-boot", "springboot", "Spring Boot"],
    "postgresql": ["postgres", "pg", "PostgreSQL", "Postgres"],
    "redis": ["Redis"],
    "neo4j": ["Neo4j"],
    "minio": ["MinIO"],
    "jwt": ["JWT", "JSON Web Token"],
    "rest": ["REST", "RESTful", "Restful"],
    "graphql": ["GraphQL", "GQL"],
    "docker": ["Docker"],
    "kubernetes": ["k8s", "K8s", "Kubernetes"],
}


class EntityResolver:
    """实体融合/消歧器 — 四级策略。"""

    async def resolve(
        self,
        new_entity: KGEntity,
        existing_entities: list[KGEntity],
    ) -> tuple[KGEntity | None, ResolutionAction]:
        """执行四级消歧策略。

        Args:
            new_entity: 新提取的实体。
            existing_entities: 已存在的实体列表。

        Returns:
            (合并后的实体, 动作)：merge=合并到已有, new=新建, referred=引用已有。
        """
        # 1. 精确匹配
        for existing in existing_entities:
            if self._exact_match(new_entity, existing):
                merged = self._merge_entities(existing, new_entity)
                logger.debug("精确匹配合并: %s -> %s", new_entity.name, existing.name)
                return merged, "merge"

        # 2. 别名匹配
        for existing in existing_entities:
            if self._alias_match(new_entity, existing):
                merged = self._merge_entities(existing, new_entity)
                logger.debug("别名匹配合并: %s -> %s", new_entity.name, existing.name)
                return merged, "merge"

        # 3. 语义相似度匹配
        for existing in existing_entities:
            similarity = self._semantic_similarity(new_entity, existing)
            if similarity >= kn_config.semantic_similarity_threshold:
                merged = self._merge_entities(existing, new_entity)
                logger.debug(
                    "语义匹配合并: %s -> %s (sim=%.2f)",
                    new_entity.name,
                    existing.name,
                    similarity,
                )
                return merged, "merge"

        # 4. 无匹配 — 返回新建
        return new_entity, "new"

    async def resolve_batch(
        self,
        new_entities: list[KGEntity],
        existing_entities: list[KGEntity],
    ) -> list[KGEntity]:
        """批量消歧。

        Args:
            new_entities: 新提取的实体列表。
            existing_entities: 已存在的实体列表。

        Returns:
            消歧后的实体列表（含合并和新实体）。
        """
        resolved: list[KGEntity] = list(existing_entities)
        for new_entity in new_entities:
            result, action = await self.resolve(new_entity, resolved)
            if action == "new" and result is not None:
                resolved.append(result)
            elif action == "merge" and result is not None:
                # 替换 merged 后的实体
                for i, e in enumerate(resolved):
                    if e.id == result.id:
                        resolved[i] = result
                        break
        return resolved

    def _exact_match(self, a: KGEntity, b: KGEntity) -> bool:
        """精确名称匹配。

        Args:
            a: 实体 A。
            b: 实体 B。

        Returns:
            是否匹配。
        """
        return a.name.lower().strip() == b.name.lower().strip()

    def _alias_match(self, a: KGEntity, b: KGEntity) -> bool:
        """别名匹配。

        Args:
            a: 实体 A。
            b: 实体 B。

        Returns:
            是否匹配。
        """
        a_lower = a.name.lower().strip()
        b_lower = b.name.lower().strip()
        # 检查别名映射
        for _, aliases in ALIAS_MAP.items():
            lower_aliases = [alias.lower() for alias in aliases]
            if a_lower in lower_aliases and b_lower in lower_aliases:
                return True
        # 检查 key 标准化
        a_key = self._normalize_key(a_lower)
        b_key = self._normalize_key(b_lower)
        return a_key == b_key

    def _semantic_similarity(self, a: KGEntity, b: KGEntity) -> float:
        """语义相似度（基于名称和描述的简单文本匹配）。

        Args:
            a: 实体 A。
            b: 实体 B。

        Returns:
            相似度分数 [0, 1]。
        """
        # 基于名称 Token 重叠的 Jaccard 相似度
        a_tokens = set(self._tokenize(a.name + " " + a.description))
        b_tokens = set(self._tokenize(b.name + " " + b.description))
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = a_tokens & b_tokens
        union = a_tokens | b_tokens
        return len(intersection) / len(union)

    @staticmethod
    def _normalize_key(name: str) -> str:
        """标准化名称用于别名匹配。

        Args:
            name: 原始名称。

        Returns:
            标准化后的 key。
        """
        return hashlib.md5(name.lower().replace("-", "").replace("_", "").replace(" ", "").encode()).hexdigest()

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单分词。

        Args:
            text: 输入文本。

        Returns:
            Token 列表。
        """
        import re

        return re.findall(r"[a-zA-Z0-9_\-]+", text.lower())

    @staticmethod
    def _merge_entities(existing: KGEntity, new_entity: KGEntity) -> KGEntity:
        """合并两个实体（保留已有信息，补充新信息）。

        Args:
            existing: 已有实体。
            new_entity: 新实体。

        Returns:
            合并后的实体。
        """
        merged = existing.model_copy(deep=True)
        # 补充描述（如新描述更长）
        if len(new_entity.description) > len(merged.description):
            merged.description = new_entity.description
        # 置信度取高值
        merged.confidence = max(merged.confidence, new_entity.confidence)
        # 合并属性
        merged.properties.update(new_entity.properties)
        return merged
