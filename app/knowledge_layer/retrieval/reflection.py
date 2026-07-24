"""检索反思裁判 — LLM 判断检索结果质量，不满足时自动修正查询。"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel

from app.core.logger import get_logger
from app.knowledge_layer.models import ScoredDoc
from app.llm_gateway import gateway

logger = get_logger("prd2tsd.knowledge.reflection")

REFLECTION_PROMPT = """你是一个检索质量反思专家。判断检索结果是否满足用户的需求。

用户需求：{query}

检索到的结果：
{results}

请判断这些结果是否满足用户的需求。

- 如果结果充分满足需求，输出：
  {{"judgment": "accept", "reason": "结果已覆盖用户需求"}}

- 如果结果不满足需求，分析缺少什么，并生成修正后的搜索查询：
  {{"judgment": "refine", "reason": "缺少XX相关信息", "refined_query": "修正后的搜索查询"}}

- 如果完全没有结果，输出：
  {{"judgment": "refine", "reason": "无检索结果", "refined_query": "放宽条件的搜索查询"}}

只返回 JSON，不要包含其他说明。"""


class ReflectionResult(BaseModel):
    """反思裁判结果。"""

    judgment: Literal["accept", "refine"]
    reason: str = ""
    refined_query: str = ""


class ReflectionJudge:
    """检索结果反思裁判。

    判断检索结果是否匹配用户意图，不匹配时生成修正后的查询并允许重新检索。
    """

    def __init__(self, model: str | None = None) -> None:
        """初始化反思裁判。

        Args:
            model: LLM 模型名。为 None 时使用默认模型。
        """
        self._model = model

    async def judge(
        self,
        query: str,
        results: list[ScoredDoc],
    ) -> ReflectionResult:
        """判断检索结果质量。

        Args:
            query: 原始用户查询。
            results: 检索结果列表。

        Returns:
            反思结果（accept 或 refine + 修正查询）。
        """
        if not results:
            logger.info("反思: 无检索结果，生成修正查询")
            return ReflectionResult(
                judgment="refine",
                reason="无检索结果",
                refined_query=query,
            )

        formatted = self._format_results(results)
        prompt = REFLECTION_PROMPT.format(query=query, results=formatted)

        try:
            response = await gateway.complete(
                prompt=prompt,
                model=self._model,
                temperature=0.1,
                max_tokens=512,
            )
            result = self._parse_response(response.content)
            logger.debug(
                "反思结果: judgment=%s, reason=%s",
                result.judgment,
                result.reason[:60],
            )
            return result
        except Exception as e:
            logger.warning("反思裁判调用失败，默认接受结果: %s", str(e))
            return ReflectionResult(judgment="accept", reason="反思裁判异常，跳过")

    def _format_results(self, results: list[ScoredDoc]) -> str:
        """格式化检索结果供 LLM 判断。

        Args:
            results: 检索结果列表。

        Returns:
            格式化后的文本。
        """
        lines: list[str] = []
        for i, doc in enumerate(results[:5]):
            text = doc.text[:200].replace("\n", " ")
            lines.append(f"[{i + 1}] (score={doc.score:.3f}) {text}")
        return "\n".join(lines)

    def _parse_response(self, response: str) -> ReflectionResult:
        """解析 LLM 返回的 JSON。

        Args:
            response: LLM 原始响应。

        Returns:
            解析后的反思结果。
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
            data: dict[str, Any] = json.loads(text)
            return ReflectionResult(
                judgment=data.get("judgment", "accept"),
                reason=data.get("reason", ""),
                refined_query=data.get("refined_query", ""),
            )
        except json.JSONDecodeError:
            logger.warning("反思结果解析失败: %s...", response[:80])
            return ReflectionResult(judgment="accept", reason="解析失败，跳过")
