"""知识检索工具 — SearchKnowledgeTool, GetEntityTool。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.result import ToolResult


class SearchKnowledgeParams(BaseModel):
    """SearchKnowledgeTool 参数模型。"""

    query: str = Field(description="搜索查询语句")
    top_k: int = Field(default=5, description="返回结果数量")
    workspace_id: str = Field(default="", description="工作空间 ID")


class SearchKnowledgeTool(BaseTool):
    """知识检索工具 — 从知识图谱/向量库中检索相关信息。"""

    name = "search_knowledge"
    description = "从知识图谱中检索与查询相关的技术文档、实体和关系信息"
    parameters = SearchKnowledgeParams
    allowed_agents = ["analysis", "planning", "generation", "evaluation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        query = params.get("query", "")
        top_k = params.get("top_k", 5)
        workspace_id = params.get("workspace_id", ctx.workspace_id)

        try:
            from app.knowledge_layer.pipeline import RetrievalPipeline

            pipeline = RetrievalPipeline()
            context = await pipeline.retrieve(
                query=query,
                mode="hybrid",
                top_k=top_k,
                workspace_id=workspace_id or ctx.workspace_id,
            )
            return ToolResult(
                success=True,
                data={
                    "results": [
                        {"text": doc.text[:500], "score": doc.score, "source": doc.source}
                        for doc in context.results
                    ],
                    "total": len(context.results),
                },
                metadata={"query": query, "top_k": top_k},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GetEntityParams(BaseModel):
    """GetEntityTool 参数模型。"""

    entity_name: str = Field(description="实体名称")
    workspace_id: str = Field(default="", description="工作空间 ID")


class GetEntityTool(BaseTool):
    """实体查询工具 — 获取知识图谱中指定实体的详细信息。"""

    name = "get_entity"
    description = "获取知识图谱中指定实体的详细信息，包括属性、关系和关联文档"
    parameters = GetEntityParams
    allowed_agents = ["analysis", "planning", "generation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        entity_name = params.get("entity_name", "")
        workspace_id = params.get("workspace_id", ctx.workspace_id)

        try:
            from app.knowledge_layer.graph_store import GraphStore

            store = GraphStore()
            entity = await store.get_entity_by_name(
                entity_name,
                workspace_id=workspace_id or ctx.workspace_id,
            )
            if entity:
                return ToolResult(
                    success=True,
                    data=entity.model_dump() if hasattr(entity, "model_dump") else entity,
                )
            return ToolResult(
                success=False,
                error=f"实体 '{entity_name}' 未找到",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
