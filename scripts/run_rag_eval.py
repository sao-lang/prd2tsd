"""RAG 评测 CLI — 跑评测 → 输出报告 → 可选反思 A/B。

Usage:
    python scripts/run_rag_eval.py --dataset tests/eval/datasets/rag_qa.json
    python scripts/run_rag_eval.py --variant '{"top_k": 5, "reflection": true}'
    python scripts/run_rag_eval.py --ab-reflection
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.logger import setup_logger
from app.evaluation.rag import RagEvaluator, load_rag_dataset

REPORTS_DIR = Path(__file__).resolve().parent.parent / "tests" / "eval" / "reports"


def _parse_variant(text: str) -> dict:
    """解析 --variant JSON 字符串。

    Args:
        text: JSON 字符串。

    Returns:
        配置 dict；空字符串返回空 dict。
    """
    return json.loads(text) if text else {}


def _dataset_version(path: str | Path) -> str:
    """读取数据集版本号。

    Args:
        path: 数据集 JSON 路径。

    Returns:
        版本字符串，缺省返回 "1.0"。
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return str(data.get("version", "1.0"))
    except (OSError, json.JSONDecodeError):
        return "1.0"


def _print_summary(report: object) -> None:
    """打印评测汇总。

    Args:
        report: RagEvalReport 实例。
    """
    summary = report.summary
    print("=== RAG 评测汇总 ===")
    print(f"样本数: {summary.samples}")
    print(f"context_precision: {summary.avg_context_precision:.3f}")
    print(f"context_recall:    {summary.avg_context_recall:.3f}")
    print(f"faithfulness:      {summary.avg_faithfulness:.3f}")
    print(f"answer_relevancy:  {summary.avg_answer_relevancy:.3f}")


async def _run(dataset_path: str, variant: dict, ab: bool) -> None:
    """执行评测主流程。

    Args:
        dataset_path: 数据集路径。
        variant: 检索配置覆盖。
        ab: 是否执行反思 A/B。
    """
    setup_logger()
    samples = load_rag_dataset(dataset_path)
    evaluator = RagEvaluator()
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    version = _dataset_version(dataset_path)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if ab:
        outcome = await evaluator.evaluate_ab_reflection(samples, variant, version)
        report_path = REPORTS_DIR / f"rag_ab_reflection_{ts}.json"
        report_path.write_text(
            json.dumps(
                {
                    "reflection_off": outcome["reflection_off"].model_dump(),
                    "reflection_on": outcome["reflection_on"].model_dump(),
                    "diff": outcome["diff"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("=== 反思 A/B 对比 ===")
        diff = outcome["diff"]
        print(
            f"diff: context_precision={diff['context_precision']:+.3f} "
            f"context_recall={diff['context_recall']:+.3f} "
            f"faithfulness={diff['faithfulness']:+.3f}"
        )
        print(f"报告: {report_path}")
        return

    report = await evaluator.evaluate_async(samples, variant, version)
    report_path = REPORTS_DIR / f"rag_eval_{ts}.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    _print_summary(report)
    print(f"报告: {report_path}")


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="RAG 检索/回答质量评测（基于 ragas）")
    parser.add_argument("--dataset", default="tests/eval/datasets/rag_qa.json", help="数据集路径")
    parser.add_argument("--variant", default="", help='检索配置覆盖，如 \'{"top_k": 5, "reflection": true}\'')
    parser.add_argument("--ab-reflection", action="store_true", help="反思开/关 A/B 对比")
    args = parser.parse_args()

    asyncio.run(_run(args.dataset, _parse_variant(args.variant), args.ab_reflection))


if __name__ == "__main__":
    main()
