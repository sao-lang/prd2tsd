"""RequirementExtractorNode — LLM 从 PRD 章节中提取需求。"""

from __future__ import annotations

import json

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.tools import call_llm_async, extract_json_from_llm
from contracts.interfaces import RequirementDetail

REQUIREMENT_PROMPT = """你是一个需求分析师。从以下 PRD 内容中提取功能需求和非功能需求。

每个需求必须包含：
- id: FR-001 / NFR-001 格式
- type: "functional" 或 "non_functional"
- category: 所属类别（如"用户管理"、"订单处理"、"性能"、"安全"）
- priority: P0/P1/P2/P3
- description: 需求描述
- actor: 涉众角色
- acceptance_criteria: 验收标准列表
- source_section: 来源章节

请以 JSON 数组格式返回，不要包含其他内容。

PRD 内容：
{text}
"""


class RequirementExtractorNode:
    """需求提取节点：LLM 从 PRD 章节中提取需求列表。"""

    async def run(self, state: AnalysisState) -> AnalysisState:
        """执行需求提取。

        Args:
            state: 当前状态，含 prd_sections。

        Returns:
            更新后的状态，含 extracted_requirements。
        """
        prd_text = state["prd_raw"][:8000]
        prompt = REQUIREMENT_PROMPT.format(text=prd_text)
        response = await call_llm_async(prompt, model="deepseek-v3")

        try:
            raw = extract_json_from_llm(response)
            data = json.loads(raw)
            if isinstance(data, list):
                requirements = [RequirementDetail(**item) for item in data]
            else:
                requirements = [RequirementDetail(**data)]
        except (json.JSONDecodeError, Exception):
            requirements = []

        return {
            **state,
            "extracted_requirements": requirements,
        }
