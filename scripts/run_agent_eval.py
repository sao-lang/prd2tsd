"""Agent 评测 CLI — 跑任务 → 过程指标 + judge 评分 → 报告。

Usage:
    python scripts/run_agent_eval.py --dataset tests/eval/datasets/agent_tasks.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.logger import setup_logger
from app.evaluation.agent import AgentEvaluator
from app.evaluation.agent.models import AgentTask

REPORTS_DIR = Path(__file__).resolve().parent.parent / "tests" / "eval" / "reports"


def _load_tasks(path: str) -> list[AgentTask]:
    """加载 Agent 评测任务。

    Args:
        path: 数据集 JSON 路径。

    Returns:
        AgentTask 列表。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [AgentTask(**task) for task in data.get("samples", [])]


async def _run(dataset_path: str) -> None:
    """执行 Agent 评测主流程。

    Args:
        dataset_path: 数据集路径。
    """
    setup_logger()
    tasks = _load_tasks(dataset_path)
    evaluator = AgentEvaluator()
    report = await evaluator.evaluate(tasks)

    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"agent_eval_{ts}.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print("=== Agent 评测汇总 ===")
    print(f"任务数: {len(report.tasks)}")
    print(f"完成率: {report.completion_rate:.2%}")
    print(f"平均迭代轮数: {report.avg_iterations}")
    print(f"人工介入率: {report.human_review_rate:.2%}")
    print(f"judge 均分: {report.avg_judge_score}")
    print(f"报告: {report_path}")


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="Agent 端到端能力评测")
    parser.add_argument("--dataset", default="tests/eval/datasets/agent_tasks.json", help="数据集路径")
    args = parser.parse_args()

    asyncio.run(_run(args.dataset))


if __name__ == "__main__":
    main()
