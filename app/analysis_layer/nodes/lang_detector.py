"""LanguageDetectorNode — ⭐ 多语言支持：检测语言并翻译英文 PRD。"""

from __future__ import annotations

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async

LANG_DETECT_PROMPT = """判断以下文本的主要语言（"中文"或"英文"或"混合"）。
只返回一个词，不要其他内容。

文本前 200 字符：
{text}
"""

TRANSLATE_PROMPT = """将以下英文 PRD 内容翻译为中文，保留 Markdown 格式。

原文：
{text}
"""


class LanguageDetectorNode:
    """语言检测节点：检测 PRD 语言，英文自动翻译为中文。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行语言检测和翻译。

        Args:
            state: 当前状态，含 prd_raw。

        Returns:
            更新后的状态（如果检测到英文，prd_raw 会被翻译）。
        """
        sample = state["prd_raw"][:200]
        prompt = LANG_DETECT_PROMPT.format(text=sample)
        lang = (await call_llm_async(prompt, model="deepseek-v3")).strip()

        if "英文" in lang and "中文" not in lang:
            trans_prompt = TRANSLATE_PROMPT.format(text=state["prd_raw"][:8000])
            translated = await call_llm_async(trans_prompt, model="deepseek-v3")
            return {
                **state,
                "prd_raw": translated,
            }

        return state
