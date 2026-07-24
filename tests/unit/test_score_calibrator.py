"""ScoreCalibrator — ⭐ 评分校准单元测试。"""

from __future__ import annotations

from app.evaluation.score_calibrator import ScoreCalibrator


def test_calibrator_first_run():
    """验证首次校准直接返回原始分数。"""
    calibrator = ScoreCalibrator()
    result = calibrator.calibrate(8.0, {"prd_coverage": 8})
    assert result["overall"] == 8.0
    assert result["dimensions"]["prd_coverage"] == 8.0


def test_calibrator_history_averaging():
    """验证历史比对加权平均。"""
    calibrator = ScoreCalibrator()
    calibrator.calibrate(8.0, {"prd_coverage": 8})
    calibrator.calibrate(7.0, {"prd_coverage": 7})

    # 第三次：历史平均 (8+7)/2=7.5，当前 6 → 校准后 (6+7.5)/2=6.75
    result = calibrator.calibrate(6.0, {"prd_coverage": 6})
    assert result["overall"] == 6.8  # round((6+7.5)/2, 1)


def test_calibrator_record():
    """验证 record 方法。"""
    calibrator = ScoreCalibrator()
    calibrator.record({"overall": 9.0})
    calibrator.record({"overall": 8.0})
    assert len(calibrator.history) == 2


def test_calibrator_empty_history():
    """验证空历史时的行为。"""
    calibrator = ScoreCalibrator()
    result = calibrator.calibrate(5.0, {})
    assert result["overall"] == 5.0
    assert result["dimensions"] == {}
