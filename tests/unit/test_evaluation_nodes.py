"""C4 Evaluation Layer — 节点单元测试。"""

from __future__ import annotations

from app.evaluation.score_calibrator import ScoreCalibrator


def test_score_calibrator_record_and_calibrate():
    """验证 ScoreCalibrator 评分校准。"""
    calibrator = ScoreCalibrator()
    result = calibrator.calibrate(8.0, {"prd_coverage": 8, "consistency": 7})
    assert result["overall"] == 8.0
    assert "prd_coverage" in result["dimensions"]

    # 第二次校准（历史比对）
    result2 = calibrator.calibrate(6.0, {"prd_coverage": 6, "consistency": 7})
    assert result2["overall"] == 7.0  # (8+6)/2


def test_score_calibrator_history():
    """验证 ScoreCalibrator 历史记录。"""
    calibrator = ScoreCalibrator()
    calibrator.record({"overall": 7.0, "prd_coverage": 7.0})
    calibrator.record({"overall": 8.0, "prd_coverage": 8.0})
    assert len(calibrator.history) == 2
