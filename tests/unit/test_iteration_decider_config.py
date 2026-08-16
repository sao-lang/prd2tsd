"""IterationDecider 配置生效回归测试（2026-08-16 条目 31）。

验证：
- 默认配置行为与历史硬编码 85/70 完全一致（行为不变）
- 自定义 pass / replan 阈值真实生效（不再硬编码）
- max_iterations 缺省取 OrchestratorConfig，且 state 显式值优先
"""

from __future__ import annotations

from app.orchestrator.iteration import IterationDecider
from app.orchestrator.state import OrchestratorConfig


def _state(
    score: float,
    consistency: float = 100.0,
    feasibility: float = 100.0,
    critical: list[str] | None = None,
    iteration_count: int = 0,
    max_iterations: int | None = None,
) -> dict:
    """构造最小 OrchestratorState（评测报告用 dict 兼容分支）。"""
    state: dict = {
        "evaluation_report": {
            "overall_score": score,
            "dimension_scores": {
                "consistency": consistency,
                "feasibility": feasibility,
            },
            "critical_issues": critical or [],
        },
        "iteration_count": iteration_count,
    }
    if max_iterations is not None:
        state["max_iterations"] = max_iterations
    return state


def test_default_thresholds_preserve_previous_behavior() -> None:
    """默认配置下行为与硬编码 85/70 一致。"""
    decider = IterationDecider()
    # >= 85 通过
    assert decider.run(_state(85.0)) == "final_assembly"
    # 70~85：维度不达标 → regenerate / replan；达标 → accept
    assert decider.run(_state(84.0, consistency=50)) == "generation"
    assert decider.run(_state(84.0, feasibility=50)) == "planning"
    assert decider.run(_state(84.0)) == "final_assembly"
    # < 70：有关键问题转人工，否则重规划
    assert decider.run(_state(69.0, critical=["security 缺失"])) == "analysis_human_review"
    assert decider.run(_state(69.0)) == "planning"


def test_custom_pass_threshold_skips_dimension_check() -> None:
    """自定义通过阈值生效：高分不再无条件通过。"""
    decider = IterationDecider(
        config=OrchestratorConfig(
            evaluation_pass_threshold=95.0,
            evaluation_replan_threshold=80.0,
        )
    )
    # 90 分高于默认 85 会直接通过；低于自定义 95 → 走中段维度判断，维度低 → regenerate
    assert decider.run(_state(90.0, consistency=60)) == "generation"
    assert decider.run(_state(90.0, consistency=96)) == "final_assembly"


def test_custom_replan_threshold_affects_dimension_check() -> None:
    """自定义重规划阈值生效：维度判断不再写死 70。"""
    decider = IterationDecider(
        config=OrchestratorConfig(evaluation_replan_threshold=80.0)
    )
    # 75 分维度：默认 70 线会通过，自定义 80 线触发 regenerate
    assert decider.run(_state(84.0, consistency=75)) == "generation"
    # 85 分维度：高于 80 线 → accept
    assert decider.run(_state(84.0, consistency=85)) == "final_assembly"


def test_max_iterations_defaults_to_config() -> None:
    """state 缺省时 max_iterations 取 OrchestratorConfig。"""
    decider = IterationDecider(config=OrchestratorConfig(max_iterations=2))
    assert decider.run(_state(0.0, iteration_count=2)) == "final_assembly"


def test_state_max_iterations_overrides_config() -> None:
    """state 显式 max_iterations 优先于配置。"""
    decider = IterationDecider(config=OrchestratorConfig(max_iterations=2))
    state = _state(0.0, iteration_count=3, max_iterations=5)
    assert decider.run(state) == "planning"
