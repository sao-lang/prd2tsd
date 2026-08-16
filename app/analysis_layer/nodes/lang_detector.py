"""LanguageDetectorNode — LangChain 多语言检测与翻译。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.analysis_layer.models import AnalysisState, LanguageResult
from app.core.logger import get_logger
from app.llm_gateway.langchain_adapter import GatewayChatModel

logger = get_logger("prd2tsd.analysis.lang_detector")

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
        """执行语言检测与英文翻译节点逻辑。"""
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
                translated = resp.content if isinstance(resp.content, str) else str(resp.content)
                return {**state, "prd_raw": translated}
            except Exception as exc:
                logger.warning("英文 PRD 翻译失败，将使用原文继续: %s", exc)

        return state
