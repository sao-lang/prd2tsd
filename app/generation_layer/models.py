"""C3 — Generation Layer 状态与结果模型。"""

from __future__ import annotations

from typing import Annotated, Any

from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    GenerationResultDetail,
    PlanningResultDetail,
    SectionOutline,
)


def merge_contents(a: dict[str, str], b: dict[str, str]) -> dict[str, str]:
    """LangGraph reducer: 合并两个章节内容 dict。"""
    merged = dict(a)
    merged.update(b)
    return merged


class GenerationState(TypedDict):
    """生成层状态（LangGraph State）。"""

    planning_result: PlanningResultDetail
    analysis_result: AnalysisResultDetail
    outline: list[SectionOutline]
    section_contents: Annotated[dict[str, str], merge_contents]  # reducer 自动合并各轮撰写的章节
    generation_result: GenerationResultDetail
    # 以下字段由 Orchestrator Adapter 注入
    task_id: str  # 任务 ID，用于 SSE 事件推送
    evaluation_feedback: dict[str, Any]  # {issues, recommendations, overall_score}
    system_prompt: str  # 租户自定义 System Prompt
    claims_constraints: list[Any]  # Claims 检索注入的约束条件
    # 以下字段由生成层节点写入
    mermaid_diagrams: dict[str, str]  # DiagramGeneratorNode 写入，FormatAssembler 消费
    code_scaffold: str  # CodeScaffoldGeneratorNode 写入
    consistency_issues: list[str]  # ConsistencyCheckerNode 写入，RevisionNode 消费
    export_formats: dict[str, str]  # FormatExporterNode 写入各格式导出内容/路径
    _section_target: SectionOutline | None  # Send() 注入的单节目标（非公开通道）
