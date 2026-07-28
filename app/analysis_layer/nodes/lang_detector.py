"""LanguageDetectorNode — LangChain 多语言检测与翻译。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, LanguageResult
from app.llm_gateway.langchain_adapter import GatewayChatModel

_DETECT_PARSER = PydanticOutputParser(pydantic_object=LanguageResult)

LANG_DETECT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "判断以下文本的主要语言。"),
    ("system", "{format_instructions}"),
    ("human", "{sample}"),
])


class LanguageDetectorNode:
    """语言检测节点。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="analysis", layer="analysis", node="lang_detect")
        self.detect_chain = LANG_DETECT_PROMPT | llm | _DETECT_PARSER
        self.translate_llm = GatewayChatModel(task_type="analysis", layer="analysis", node="translate")

    async def run(self, state: AnalysisState) -> AnalysisState:
        sample = state["prd_raw"][:200]
        try:
            result: LanguageResult = await self.detect_chain.ainvoke({
                "sample": sample,
                "format_instructions": _DETECT_PARSER.get_format_instructions(),
            })
            lang = result.language
        except Exception:
            lang = "zh"

        if lang == "en":
            try:
                from langchain_core.messages import HumanMessage, SystemMessage

                resp = await self.translate_llm.ainvoke([
                    SystemMessage(content="将以下英文 PRD 内容翻译为中文，保留 Markdown 格式。"),
                    HumanMessage(content=state["prd_raw"][:8000]),
                ])
                return {**state, "prd_raw": resp.content}
            except Exception:
                pass

        return state
