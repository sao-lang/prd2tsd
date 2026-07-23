"""单元测试 — Claims/Covariates 提取。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.knowledge_layer.ingestion.claims_extractor import ClaimsExtractor
from app.knowledge_layer.models import KGEntity, TextUnit


@pytest.fixture
def extractor() -> ClaimsExtractor:
    """创建 Claims 提取器。"""
    return ClaimsExtractor()


@pytest.fixture
def sample_text_unit() -> TextUnit:
    """创建示例 TextUnit。"""
    return TextUnit(
        id="tu1",
        text="系统使用 PostgreSQL 数据库，它比 MySQL 性能更好。采用 JWT Token 进行认证。",
        entities=["e1", "e2"],
    )


@pytest.fixture
def sample_entities() -> list[KGEntity]:
    """创建示例实体。"""
    return [
        KGEntity(id="e1", name="PostgreSQL", type="TechStack"),
        KGEntity(id="e2", name="JWT", type="TechStack"),
    ]


class TestClaimsExtractor:
    """Claims 提取器测试。"""

    async def test_parse_response_valid_json(self, extractor) -> None:
        """验证解析有效 JSON。"""
        response = '[{"subject": "PostgreSQL", "claim_type": "comparison", "content": "PostgreSQL 比 MySQL 性能更好"}]'
        data = extractor._parse_response(response)
        assert len(data) == 1
        assert data[0]["subject"] == "PostgreSQL"

    async def test_parse_response_with_code_block(self, extractor) -> None:
        """验证解析含代码块的 JSON。"""
        response = '```json\n[{"subject": "JWT", "claim_type": "decision", "content": "采用 JWT Token 认证"}]\n```'
        data = extractor._parse_response(response)
        assert len(data) == 1
        assert data[0]["subject"] == "JWT"

    async def test_parse_response_invalid(self, extractor) -> None:
        """验证解析无效 JSON 返回空列表。"""
        data = extractor._parse_response("not json")
        assert data == []

    async def test_extract_with_mocked_llm(self, extractor, sample_text_unit, sample_entities) -> None:
        """验证 Mock LLM 后的提取流程。"""
        mock_response = '```json\n[{"subject": "PostgreSQL", "object": "MySQL", "claim_type": "comparison", "content": "PostgreSQL 比 MySQL 性能更好", "confidence": 0.9}]\n```'

        with patch("app.knowledge_layer.ingestion.claims_extractor.llm_complete", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            claims = await extractor._extract_from_text_unit(
                sample_text_unit,
                {"PostgreSQL": "e1", "JWT": "e2"},
            )
            assert len(claims) == 1
            assert claims[0].claim_type == "comparison"
            assert claims[0].subject_entity_id == "e1"

    async def test_empty_text_unit(self, extractor, sample_entities) -> None:
        """验证空 TextUnit 无 Claims。"""
        empty_tu = TextUnit(id="empty", text="", entities=[])
        name_to_id = {e.name: e.id for e in sample_entities}
        claims = await extractor._extract_from_text_unit(empty_tu, name_to_id)
        assert len(claims) == 0
