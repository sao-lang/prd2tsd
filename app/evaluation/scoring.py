"""ScoringNode — 10 维加权综合评分。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.evaluation.models import EvaluationState
from app.evaluation.score_calibrator import ScoreCalibrator
from app.evaluation.tools import call_llm


def _search_json(text: str) -> re.Match[str] | None:
    """搜索 JSON 大括号块。"""
    return re.search(r"\{.*\}", text, re.DOTALL)

SCORING_PROMPT = """你是一个技术方案评审专家。对以下技术方案进行 10 维评分（每维 0-10）。

评分维度：
1. prd_coverage: PRD 需求覆盖率
2. consistency: 方案内部一致性
3. feasibility: 技术可行性
4. architecture_quality: 架构质量
5. security: 安全合规
6. cost: 成本合理性
7. implementability: 可实施性
8. tech_advancement: 技术先进性
9. legal_compliance: 法律合规
10. completeness: 文档完整度

返回 JSON：
{{
  "dimensions": {{
    "prd_coverage": 8,
    "consistency": 7,
    ...
  }},
  "overall": 7.5,
  "conclusion": "通过",
  "p0_coverage": 0.9,
  "issues": [{{"dimension": "security", "desc": "...", "severity": "high"}}],
  "recommendations": ["建议..."]
}}

仅返回 JSON。
"""


class ScoringNode:
    """10 维加权评分节点（汇总各子节点评分 + LLM 综合评分）。"""

    def __init__(self) -> None:
        self.calibrator = ScoreCalibrator()

    async def run(self, state: EvaluationState) -> EvaluationState:
        """执行 10 维评分。

        优先使用各子节点已收集的 dimension_scores，
        缺失维度由 LLM 补充评分。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 evaluation_report。
        """
        from contracts.interfaces import EvaluationReportDetail

        # 1. 从各子节点收集已有评分
        collected = state.get("dimension_scores", {})
        required_dims = [
            "prd_coverage", "consistency", "feasibility", "architecture_quality",
            "security", "cost", "implementability", "tech_advancement",
            "legal_compliance", "completeness",
        ]

        # 2. LLM 补全缺失维度
        prompt = SCORING_PROMPT
        response = await call_llm(prompt, model="gpt-4o-mini")

        try:
            json_match = _search_json(response)
            if json_match:
                data: dict[str, Any] = json.loads(json_match.group())
                llm_dims = data.get("dimensions", {})
                overall = float(data.get("overall", 0))
                conclusion = data.get("conclusion", "不通过")
                p0_cov = float(data.get("p0_coverage", 0))
                issues = data.get("issues", [])
                recs = data.get("recommendations", [])

                # 合并：子节点评分优先，LLM 补充缺失
                merged = {}
                for dim in required_dims:
                    if dim in collected:
                        merged[dim] = collected[dim]
                    elif dim in llm_dims:
                        merged[dim] = float(llm_dims[dim])
                    else:
                        merged[dim] = 5.0

                # 评分校准
                calibrated = self.calibrator.calibrate(overall, merged)

                report = EvaluationReportDetail(
                    overall_score=calibrated["overall"],
                    dimension_scores=calibrated["dimensions"],
                    conclusion=conclusion,
                    p0_coverage=p0_cov,
                    critical_issues=issues,
                    recommendations=recs,
                )
            else:
                report = EvaluationReportDetail()
        except (json.JSONDecodeError, Exception):
            report = EvaluationReportDetail()

        return {
            **state,
            "evaluation_report": report,
        }
