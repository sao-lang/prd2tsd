"""DomainClassifierNode — LLM 对 PRD 进行领域分类。"""

from __future__ import annotations

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async

DOMAIN_PROMPT = """分析以下 PRD 内容，判断其所属领域标签（如电商、金融、医疗、教育、IoT、企业服务等）。
用逗号分隔返回，最多 3 个标签，不要其他内容。

PRD 内容：
{text}
"""


class DomainClassifierNode:
    """领域分类节点：LLM 判断 PRD 所属领域。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行领域分类。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 domain_tags。
        """
        prd_text = state["prd_raw"][:3000]
        prompt = DOMAIN_PROMPT.format(text=prd_text)
        response = await call_llm_async(prompt, model="deepseek-v3")

        tags = [t.strip() for t in response.split(",") if t.strip()]
        if not tags:
            tags = ["通用"]

        return {
            **state,
            "domain_tags": tags,
        }
