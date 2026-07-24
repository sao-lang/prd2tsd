"""C4 — Evaluation Layer（评测层）。

对 AnalysisResult + PlanningResult + GenerationResult 进行
10 维综合评分，生成 EvaluationReport。
"""

from app.evaluation.agent_graph import build_evaluation_graph, evaluation_graph

__all__ = ["build_evaluation_graph", "evaluation_graph"]
