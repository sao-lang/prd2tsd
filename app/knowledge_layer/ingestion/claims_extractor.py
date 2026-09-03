"""Claims/Covariates 提取 — PRD 中的决策性断言提取。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.models import Chunk, Claim
from app.llm_gateway import gateway

logger = get_logger("prd2tsd.knowledge.claims_extractor")

CLAIMS_EXTRACTION_PROMPT = """你是一个技术文档断言提取专家。从以下文本中提取所有明确的决策性断言。

断言类型：
- decision: 明确的选型决策（如"使用 X 而不是 Y"）
- specification: 技术规格说明（如"支持 OAuth 2.0"）
- constraint: 约束条件（如"延迟 < 200ms"）
- comparison: 对比评估（如"X 比 Y 性能好 3 倍"）
- prediction: 预测性断言（如"预计 QPS 将达到 10000"）

请以 JSON 数组格式返回，每个断言包含：
{{
  "subject": "主体（技术实体或组件名）",
  "claim_type": "断言类型",
  "content": "断言的精确原文或摘要",
  "object": "客体（可选，如对比/约束的目标）"
}}

文本：
{text}

只返回 JSON 数组。"""


class ClaimsExtractor:
    """Claims 提取器 — 从文档分块中提取决策性断言。"""

    def __init__(self, model: str | None = None) -> None:
        """初始化 Claims 提取器。

        Args:
            model: LLM 模型名（可选）。
        """
        self._model = model

    async def extract(self, chunks: list[Chunk], workspace_id: str = "") -> list[Claim]:
        """从分块中提取 Claims。

        Args:
            chunks: 文档分块列表。
            workspace_id: 工作空间 ID，用于 Gateway 治理隔离。

        Returns:
            提取的 Claim 列表。
        """
        all_claims: list[Claim] = []
        for chunk in chunks:
            claims = await self._extract_from_chunk(chunk, workspace_id)
            all_claims.extend(claims)

        logger.info("Claims 提取完成: %d claims", len(all_claims))
        return all_claims

    async def _extract_from_chunk(self, chunk: Chunk, workspace_id: str = "") -> list[Claim]:
        """从单个分块中提取 Claims。"""
        prompt = CLAIMS_EXTRACTION_PROMPT.format(text=chunk.text[:2000])
        try:
            resp = await gateway.complete(
                prompt=prompt,
                task_type="default",
                workspace_id=workspace_id,
                layer="knowledge",
                node="claims_extractor",
                model=self._model,
                temperature=0.1,
                max_tokens=2048,
            )
            data = self._parse_response(resp.content)
        except Exception as exc:
            logger.warning("Claims 提取失败 (chunk %d): %s", chunk.index, exc)
            return []

        claims: list[Claim] = []
        for item in data:
            claim = Claim(
                id=str(uuid.uuid4()),
                subject=item.get("subject", ""),
                claim_type=item.get("claim_type", "specification"),
                content=item.get("content", ""),
                object=item.get("object", ""),
                source_text_unit_id=chunk.id,
            )
            if claim.subject and claim.content:
                claims.append(claim)
        return claims

    @staticmethod
    def _parse_response(response: str) -> list[dict[str, Any]]:
        """解析 LLM JSON 响应。"""
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
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
