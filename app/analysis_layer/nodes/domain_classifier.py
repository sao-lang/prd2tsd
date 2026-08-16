"""DomainClassifierNode — LangChain 对 PRD 进行领域分类。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, DomainResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_PARSER = PydanticOutputParser(pydantic_object=DomainResult)

DOMAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "分析以下 PRD 内容，判断其所属领域（如电商、金融、医疗、教育等）。"),
    ("system", "{format_instructions}"),
    ("human", "{prd_text}"),
])


class DomainClassifierNode:
    """领域分类节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="domain")
        self.chain = DOMAIN_PROMPT | llm | _PARSER

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行领域分类节点逻辑。"""
        prd_text = state["prd_raw"][:3000]
        try:
            result: DomainResult = await self.chain.ainvoke({
                "prd_text": prd_text,
                "format_instructions": _PARSER.get_format_instructions(),
            })
            tags = result.domain_tags or [result.primary_domain or "通用"]
            return {**state, "domain_tags": tags}
        except Exception:
            return {**state, "domain_tags": ["通用"]}
