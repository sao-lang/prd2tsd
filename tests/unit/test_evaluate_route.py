"""评测路由回归测试。

回归：POST /api/v1/evaluate 不带 analysis_result 时，
构造 AnalysisResultDetail() 缺少必填字段导致 500。
"""

from __future__ import annotations

import pytest

import app.api.routes.evaluate as evaluate_module
from app.api.routes.evaluate import EvaluateRequest, EvaluateResponse, evaluate_generation
from contracts.interfaces import AnalysisResultDetail, GenerationResultDetail


class _FakeEvaluationGraph:
    """替代 evaluation_graph 的桩，避免真实 LLM 调用。"""

    async def ainvoke(self, state: dict) -> dict:
        return {"evaluation_report": None, "dimension_scores": {}}


@pytest.mark.asyncio
async def test_evaluate_without_analysis_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """仅传 generation_result 时不应抛 ValidationError。"""
    monkeypatch.setattr(evaluate_module, "evaluation_graph", _FakeEvaluationGraph())

    req = EvaluateRequest(generation_result=GenerationResultDetail(content="测试内容"))
    result = await evaluate_generation(req, current_user=None)  # type: ignore[arg-type]

    assert isinstance(result, EvaluateResponse)
    assert result.evaluation_report is None
    assert result.dimension_scores == {}


@pytest.mark.asyncio
async def test_evaluate_with_analysis_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """带 analysis_result 时正常传递。"""
    captured: dict = {}

    class _CapturingGraph:
        async def ainvoke(self, state: dict) -> dict:
            captured.update(state)
            return {"evaluation_report": None, "dimension_scores": {}}

    monkeypatch.setattr(evaluate_module, "evaluation_graph", _CapturingGraph())
    req = EvaluateRequest(
        analysis_result=AnalysisResultDetail(project_name="项目", summary="摘要"),
        generation_result=GenerationResultDetail(content="测试内容"),
    )

    result = await evaluate_generation(req, current_user=None)  # type: ignore[arg-type]

    assert isinstance(result, EvaluateResponse)
    assert captured["analysis_result"].project_name == "项目"
