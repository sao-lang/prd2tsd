"""RAG 评测模块单元测试（mock 检索/LLM/deepeval）。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluation.rag import RagEvaluator, load_rag_dataset
from app.evaluation.rag.models import RagSample

DATASET = Path(__file__).resolve().parent.parent / "eval" / "datasets" / "rag_qa.json"


def _metric_data(name: str, score: float) -> SimpleNamespace:
    """构造 deepeval MetricData 的最小替身。"""
    return SimpleNamespace(name=name, score=score)


def test_load_rag_dataset() -> None:
    """验证黄金数据集加载。"""
    samples = load_rag_dataset(DATASET)
    assert len(samples) >= 10
    assert samples[0].id
    assert samples[0].query
    assert samples[0].reference_answer


def test_to_deepeval_test_cases() -> None:
    """验证 deepeval 测试用例组装。"""
    samples = [RagSample(id="s1", query="q", reference_answer="a")]
    evaluator = RagEvaluator()
    cases = evaluator.to_deepeval_test_cases(samples, [["ctx1"]], ["ans"])
    assert len(cases) == 1
    assert cases[0].name == "s1"
    assert cases[0].input == "q"
    assert cases[0].actual_output == "ans"
    assert cases[0].expected_output == "a"
    assert cases[0].retrieval_context == ["ctx1"]


def test_evaluate_report_structure() -> None:
    """验证 evaluate 生成报告结构（mock deepeval 分数）。"""
    samples = [
        RagSample(id="s1", query="q1", reference_answer="a1"),
        RagSample(id="s2", query="q2", reference_answer="a2"),
    ]
    fake_result = MagicMock()
    fake_result.test_results = [
        MagicMock(
            metrics_data=[
                _metric_data("Contextual Precision", 0.8),
                _metric_data("Contextual Recall", 0.7),
                _metric_data("Faithfulness", 0.9),
                _metric_data("Answer Relevancy", 0.85),
            ]
        ),
        MagicMock(
            metrics_data=[
                _metric_data("Contextual Precision", 0.6),
                _metric_data("Contextual Recall", 0.5),
                _metric_data("Faithfulness", 0.8),
                _metric_data("Answer Relevancy", 0.75),
            ]
        ),
    ]

    evaluator = RagEvaluator()
    with patch("app.evaluation.rag.evaluator.evaluate", return_value=fake_result):
        report = evaluator.evaluate(
            samples=samples,
            contexts=[["c1", "c2"], ["c3"]],
            answers=["ans1", "ans2"],
            config={"top_k": 5},
        )

    assert len(report.queries) == 2
    assert report.queries[0].context_precision == 0.8
    assert report.queries[0].retrieved_count == 2
    assert report.queries[1].retrieved_count == 1
    assert report.summary.samples == 2
    assert report.summary.avg_faithfulness == pytest.approx(0.85)
    assert report.config["top_k"] == 5
    assert report.dataset_version == "1.0"


def test_evaluate_missing_scores_default_zero() -> None:
    """验证缺分样本默认 0.0（边界）。"""
    samples = [RagSample(id="s1", query="q", reference_answer="a")]
    fake_result = MagicMock()
    fake_result.test_results = [MagicMock(metrics_data=[])]

    evaluator = RagEvaluator()
    with patch("app.evaluation.rag.evaluator.evaluate", return_value=fake_result):
        report = evaluator.evaluate(samples, [["c"]], ["ans"])

    assert report.queries[0].faithfulness == 0.0
    assert report.queries[0].answer_relevancy == 0.0


def test_build_judge_model_none_without_key() -> None:
    """验证未配置 judge key 时返回 None（异常分支）。"""
    evaluator = RagEvaluator()
    with patch("app.core.config.Settings.get_model_config_env",
        return_value={"api_key": "", "base_url": "", "default_model": "gpt-4o-mini"},
    ):
        assert evaluator._build_judge_model() is None


async def test_evaluate_async_retrieves_and_answers() -> None:
    """验证异步全流程（检索 + 回答 + 评分）。"""
    samples = [RagSample(id="s1", query="q", reference_answer="a")]
    evaluator = RagEvaluator()
    ctx = MagicMock()
    ctx.results = [MagicMock(text="c1")]
    ctx.total_tokens = 10

    real_report = MagicMock()
    with (
        patch.object(
            evaluator,
            "retrieve_and_answer",
            AsyncMock(return_value=(ctx, "ans", 2)),
        ) as mock_ra,
        patch.object(evaluator, "evaluate", return_value=real_report) as mock_eval,
    ):
        report = await evaluator.evaluate_async(samples, {"top_k": 3}, dataset_version="1.1")

    assert report is real_report
    mock_ra.assert_awaited_once()
    mock_eval.assert_called_once()
    # 验证传递了正确的上下文与回答
    _, kwargs = mock_eval.call_args
    assert kwargs["contexts"] == [["c1"]]
    assert kwargs["answers"] == ["ans"]


def test_apply_config_toggles_reflection() -> None:
    """验证 reflection 配置控制反思轮数。"""
    evaluator = RagEvaluator()
    evaluator._apply_config({"reflection": True})
    assert evaluator._pipeline.max_reflection_rounds == 2
    evaluator._apply_config({"reflection": False})
    assert evaluator._pipeline.max_reflection_rounds == 0

