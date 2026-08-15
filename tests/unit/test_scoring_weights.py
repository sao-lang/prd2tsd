"""ScoringNode 显式加权回归测试。"""

from __future__ import annotations

import pytest

from app.evaluation.scoring import DIM_WEIGHTS, ScoringNode


async def _noop_history(limit: int = 10):
    return []


async def _noop_save(**kwargs):
    return None


async def _fake_call_llm(prompt, model):
    return (
        '{"dimensions": {"prd_coverage": 8, "consistency": 6, "feasibility": 4, '
        '"architecture_quality": 5, "security": 7, "cost": 6, "implementability": 5, '
        '"tech_advancement": 6, "legal_compliance": 8, "completeness": 7}, '
        '"overall": 9.9, "conclusion": "通过", "p0_coverage": 0.8, '
        '"issues": [], "recommendations": []}'
    )


@pytest.mark.asyncio
async def test_weighted_overall(monkeypatch: pytest.MonkeyPatch) -> None:
    """总分应等于 DIM_WEIGHTS 加权和（而非 LLM 自报 overall）。"""
    monkeypatch.setattr(
        "app.evaluation.scoring.call_llm",
        _fake_call_llm,
    )
    # scoring.py 在 run() 内从 score_history 导入，需 patch 源模块
    monkeypatch.setattr("app.evaluation.score_history.load_recent_scores", _noop_history)
    monkeypatch.setattr("app.evaluation.score_history.save_evaluation_score", _noop_save)

    dims = {
        "prd_coverage": 8, "consistency": 6, "feasibility": 4, "architecture_quality": 5,
        "security": 7, "cost": 6, "implementability": 5, "tech_advancement": 6,
        "legal_compliance": 8, "completeness": 7,
    }
    state = {
        "analysis_result": None,
        "planning_result": None,
        "generation_result": None,
        "evaluation_report": None,
        "dimension_scores": {},
    }
    out = await ScoringNode().run(state)
    report = out["evaluation_report"]

    expected = round(sum(dims[d] * w for d, w in DIM_WEIGHTS.items()), 1)
    assert report.overall_score == expected, f"期望 {expected}，实际 {report.overall_score}"
