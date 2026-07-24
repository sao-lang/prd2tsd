"""ConstraintAnalyzerNode — LLM 从 PRD 中提取约束条件。"""

from __future__ import annotations

import json

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async, extract_json_from_llm
from contracts.interfaces import ConstraintDetail

CONSTRAINT_PROMPT = """你是一个需求分析师。从以下 PRD 内容中提取技术/性能/时间/预算/合规/团队等方面的约束条件。

每个约束必须包含：
- type: "technical"/"performance"/"time"/"budget"/"compliance"/"team"
- description: 约束描述
- severity: "must"/"should"/"could"
- source_section: 来源章节

请以 JSON 数组格式返回。

PRD 内容：
{text}
"""


class ConstraintAnalyzerNode:
    """约束提取节点：LLM 提取约束条件。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行约束提取。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 extracted_constraints。
        """
        prd_text = state["prd_raw"][:6000]
        prompt = CONSTRAINT_PROMPT.format(text=prd_text)
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            raw = extract_json_from_llm(response)
            data = json.loads(raw)
            constraints = [ConstraintDetail(**item) for item in (data if isinstance(data, list) else [data])]
        except (json.JSONDecodeError, Exception):
            constraints = []

        return {
            **state,
            "extracted_constraints": constraints,
        }
