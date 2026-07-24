"""评测路由 — POST /api/v1/evaluate。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user
from app.evaluation.agent_graph import evaluation_graph
from app.models.user import User
from contracts.interfaces import (
    AnalysisResultDetail,
    EvaluationReportDetail,
    GenerationResultDetail,
    PlanningResultDetail,
)

router = APIRouter(prefix="/api/v1", tags=["evaluate"])


class EvaluateRequest(BaseModel):
    """评测请求体。"""

    analysis_result: AnalysisResultDetail | None = None
    planning_result: PlanningResultDetail | None = None
    generation_result: GenerationResultDetail | None = Field(..., description="待评测的生成结果")


class EvaluateResponse(BaseModel):
    """评测响应。"""

    evaluation_report: EvaluationReportDetail | None = None
    dimension_scores: dict[str, float] = Field(default_factory=dict)


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_generation(
    req: EvaluateRequest,
    current_user: User = Depends(get_current_user),
) -> EvaluateResponse:
    """对已有方案进行评测。

    调用 Evaluation Layer 做覆盖度/一致性/可行性等维度评分。
    """
    input_state = {
        "analysis_result": req.analysis_result or AnalysisResultDetail(),
        "planning_result": req.planning_result or PlanningResultDetail(),
        "generation_result": req.generation_result,
        "evaluation_report": EvaluationReportDetail(),
        "dimension_scores": {},
    }

    result = await evaluation_graph.ainvoke(input_state)

    report = result.get("evaluation_report")
    dim_scores = result.get("dimension_scores", {})

    return EvaluateResponse(
        evaluation_report=report,
        dimension_scores=dim_scores,
    )
