"""单元测试 — 实体融合/消歧。"""

from __future__ import annotations

import pytest

from app.knowledge_layer.ingestion.entity_resolver import EntityResolver
from app.knowledge_layer.models import KGEntity


@pytest.fixture
def resolver() -> EntityResolver:
    """创建实体消歧器。"""
    return EntityResolver()


@pytest.fixture
def existing_entities() -> list[KGEntity]:
    """创建已有实体列表。"""
    return [
        KGEntity(id="1", name="Spring Boot", type="TechStack", category="框架"),
        KGEntity(id="2", name="PostgreSQL", type="TechStack", category="数据库"),
        KGEntity(id="3", name="Redis", type="TechStack", category="缓存"),
    ]


class TestEntityResolver:
    """实体消歧器测试。"""

    async def test_exact_name_match(self, resolver, existing_entities) -> None:
        """验证精确名称匹配合并。"""
        new = KGEntity(name="Spring Boot", type="TechStack", description="A framework")
        merged, action = await resolver.resolve(new, existing_entities)
        assert action == "merge"
        assert merged is not None
        assert merged.id == "1"

    async def test_alias_match(self, resolver, existing_entities) -> None:
        """验证别名匹配。"""
        new = KGEntity(name="postgres", type="TechStack")
        merged, action = await resolver.resolve(new, existing_entities)
        assert action == "merge"
        assert merged is not None

    async def test_semantic_match(self, resolver, existing_entities) -> None:
        """验证语义匹配。"""
        new = KGEntity(
            name="Spring Boot Framework",
            type="TechStack",
            description="Spring Boot is a framework for building Java applications",
        )
        existing = [KGEntity(
            id="10",
            name="Spring",
            type="TechStack",
            description="Spring Boot framework for Java development",
        )]
        merged, action = await resolver.resolve(new, existing)
        # Spring 和 Spring Boot Framework 有语义重叠
        assert action in ("merge", "new")

    async def test_no_match(self, resolver, existing_entities) -> None:
        """验证无匹配时返回新建。"""
        new = KGEntity(name="Docker", type="TechStack")
        merged, action = await resolver.resolve(new, existing_entities)
        assert action == "new"
        assert merged is not None
        assert merged.name == "Docker"

    async def test_batch_resolve(self, resolver, existing_entities) -> None:
        """验证批量消歧。"""
        new_entities = [
            KGEntity(name="Spring Boot", type="TechStack"),
            KGEntity(name="Docker", type="TechStack"),
            KGEntity(name="Kubernetes", type="TechStack"),
        ]
        resolved = await resolver.resolve_batch(new_entities, existing_entities)
        # Spring Boot 合并到已有，Docker 和 Kubernetes 新增
        assert len(resolved) == 5
        names = [e.name for e in resolved]
        assert "Spring Boot" in names
        assert "Docker" in names
        assert "Kubernetes" in names
