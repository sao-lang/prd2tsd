"""Query Rewriter — 生成多条子查询以提升召回。"""

from __future__ import annotations

from app.core.llm import llm_complete
from app.core.logger import get_logger

logger = get_logger("prd2tsd.knowledge.rewriter")

REWRITE_PROMPT = """你是一个搜索查询重写专家。根据原始查询，生成 3 条不同的子查询，以提升知识图谱检索的召回率。

原始查询：{query}

要求：
1. 每条子查询从不同角度表达原始意图
2. 使用同义词和不同表述方式
3. 保持技术术语准确
4. 每条一行，不要编号

返回格式：
子查询1
子查询2
子查询3"""


class QueryRewriter:
    """Query Rewriter — 生成多条子查询。"""

    def __init__(self, model: str | None = None) -> None:
        """初始化重写器。

        Args:
            model: LLM 模型名。为 None 时使用默认模型。
        """
        self._model = model

    async def rewrite(self, query: str) -> list[str]:
        """重写查询生成多条子查询。

        Args:
            query: 原始查询。

        Returns:
            子查询列表（至少包含原始查询）。
        """
        try:
            response = await llm_complete(
                prompt=REWRITE_PROMPT.format(query=query),
                model=self._model,
                temperature=0.3,
                max_tokens=512,
            )
            lines = [line.strip() for line in response.strip().split("\n") if line.strip()]
            # 确保原始查询也在列表中
            all_queries = [query] + [line for line in lines if line.lower() != query.lower()]
            logger.debug("查询重写: %s -> %s", query, all_queries[:5])
            return all_queries[:5]
        except Exception as e:
            logger.warning("查询重写失败: %s", str(e))
            return [query]
