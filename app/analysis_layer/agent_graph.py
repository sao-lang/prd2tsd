"""C1 — Analysis Layer LangGraph StateGraph。"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.analysis_layer.models import AnalysisState
from app.analysis_layer.nodes import (
    AnalysisResultAssemblerNode,
    ClarityCheckerNode,
    ConstraintAnalyzerNode,
    DependencyAnalyzerNode,
    DocumentParserNode,
    DomainClassifierNode,
    EffortEstimatorNode,
    LanguageDetectorNode,
    RequirementExtractorNode,
    RequirementQualityNode,
    StakeholderAnalyzerNode,
)

# 实例化所有 Node
parse_node = DocumentParserNode()
lang_detector = LanguageDetectorNode()
req_extractor = RequirementExtractorNode()
constraint_analyzer = ConstraintAnalyzerNode()
dep_analyzer = DependencyAnalyzerNode()
domain_classifier = DomainClassifierNode()
quality_scorer = RequirementQualityNode()
effort_estimator = EffortEstimatorNode()
stakeholder_analyzer = StakeholderAnalyzerNode()
clarity_checker = ClarityCheckerNode()
result_assembler = AnalysisResultAssemblerNode()


def build_analysis_graph() -> StateGraph:
    """构建并编译 Analysis Layer StateGraph。

    C1 链路：
    Parse → LangDetect → Requirement → Constraint → Dependency
    → Domain → Quality → Effort → Stakeholder → Clarity → Assemble

    Returns:
        编译后的 StateGraph。
    """
    graph = StateGraph(AnalysisState)

    # 注册节点
    graph.add_node("parse", parse_node.run)
    graph.add_node("lang_detect", lang_detector.run)
    graph.add_node("requirement", req_extractor.run)
    graph.add_node("constraint", constraint_analyzer.run)
    graph.add_node("dependency", dep_analyzer.run)
    graph.add_node("domain", domain_classifier.run)
    graph.add_node("quality", quality_scorer.run)
    graph.add_node("effort", effort_estimator.run)
    graph.add_node("stakeholder", stakeholder_analyzer.run)
    graph.add_node("clarity", clarity_checker.run)
    graph.add_node("assemble", result_assembler.run)

    # 定义链路
    graph.set_entry_point("parse")
    graph.add_edge("parse", "lang_detect")
    graph.add_edge("lang_detect", "requirement")
    graph.add_edge("requirement", "constraint")
    graph.add_edge("constraint", "dependency")
    graph.add_edge("dependency", "domain")
    graph.add_edge("domain", "quality")
    graph.add_edge("quality", "effort")
    graph.add_edge("effort", "stakeholder")
    graph.add_edge("stakeholder", "clarity")
    graph.add_edge("clarity", "assemble")
    graph.add_edge("assemble", END)

    return graph


# 编译一次供测试使用
analysis_graph = build_analysis_graph().compile()
