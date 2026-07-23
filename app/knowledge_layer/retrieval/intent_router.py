"""搜索意图路由 — 判断查询适合 local / global / hybrid 模式。"""

from __future__ import annotations

from app.core.logger import get_logger

logger = get_logger("prd2tsd.knowledge.intent_router")

# 宽泛查询关键词 — 指向 global search
GLOBAL_KEYWORDS = [
    "整体", "架构", "概述", "总结", "概括", "综述",
    "所有", "全部", "整体架构", "系统设计", "总体",
    "architecture", "overview", "summary", "overall",
]

# 具体实体查询关键词 — 指向 local search
LOCAL_KEYWORDS = [
    "什么", "如何", "怎样", "哪些", "哪个",
    "什么是", "什么是", "怎么", "how", "what",
    "技术栈", "组件", "模块", "服务", "接口",
]


class IntentRouter:
    """搜索意图路由器。"""

    def route(self, query: str) -> str:
        """根据查询文本判断搜索模式。

        Args:
            query: 用户查询。

        Returns:
            搜索模式: local / global / hybrid。
        """
        query_lower = query.lower().strip()

        # 检查全局关键词
        for keyword in GLOBAL_KEYWORDS:
            if keyword in query_lower:
                logger.debug("意图路由: global (keyword=%s)", keyword)
                return "global"

        # 检查局部关键词
        for keyword in LOCAL_KEYWORDS:
            if keyword in query_lower:
                logger.debug("意图路由: local (keyword=%s)", keyword)
                return "local"

        # 短查询（< 5 字）偏向 local
        if len(query) < 5:
            return "local"

        # 默认 hybrid
        return "hybrid"
