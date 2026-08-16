"""C3 — Generation Layer LangGraph StateGraph。

使用 Send() 实现并行章节撰写：
Outline → FanOutSections → [SectionWriter × n（并行）] → DiagramGenerator → …
"""

from __future__ import annotations

from typing import Any

from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from app.generation_layer.models import GenerationState
from app.generation_layer.nodes import (
    CodeScaffoldGeneratorNode,
    ConsistencyCheckerNode,
    DiagramGeneratorNode,
    FormatAssemblerNode,
    FormatExporterNode,
    OutlineGeneratorNode,
    RevisionNode,
    SectionWriterNode,
)
from app.observability.tracing import trace_node
from contracts.interfaces import SectionOutline

outline_node = OutlineGeneratorNode()
section_writer = SectionWriterNode()
diagram_generator = DiagramGeneratorNode()
code_scaffold = CodeScaffoldGeneratorNode()
consistency_checker = ConsistencyCheckerNode()
revision_node = RevisionNode()
format_assembler = FormatAssemblerNode()
format_exporter = FormatExporterNode()


# ── Fan-Out 函数 ──


def fan_out_sections(state: GenerationState) -> list[Send]:
    """扇出：为每个未写的章节创建一个 Send，并行执行 SectionWriter。

    利用 reducer merge_contents 自动合并并行写入的章节内容。

    Args:
        state: 当前状态。

    Returns:
        Send 列表（每个指向 section_writer），若无未写章节则直接路由到 diagram。
    """
    outline = state.get("outline", [])
    existing = state.get("section_contents", {})

    sends: list[Send] = []
    for section in outline:
        if isinstance(section, SectionOutline) and section.section_id not in existing:
            # 注入 _section_target 让 Worker 知道写哪节
            sends.append(Send("section_writer", {**state, "_section_target": section}))

    # 所有章节已写完 → 跳过 writer 直接进入后续节点
    if not sends:
        sends.append(Send("diagram", state))

    return sends


def build_generation_graph() -> StateGraph[GenerationState, Any, Any, Any]:
    """构建并编译 Generation Layer StateGraph（Send 并行版）。

    C3 链路：
    Outline → FanOutSections → [SectionWriter × n 并行] → DiagramGenerator
    → CodeScaffold → ConsistencyChecker → Revision → FormatAssembler → FormatExporter
    """
    graph = StateGraph(GenerationState)

    graph.add_node("outline", trace_node("outline")(outline_node.run))
    graph.add_node("section_writer", trace_node("section_writer")(section_writer.run))
    graph.add_node("diagram", trace_node("diagram")(diagram_generator.run))
    graph.add_node("code_scaffold", trace_node("code_scaffold")(code_scaffold.run))
    graph.add_node("consistency", trace_node("consistency")(consistency_checker.run))
    graph.add_node("revision", trace_node("revision")(revision_node.run))
    graph.add_node("assemble", trace_node("assemble")(format_assembler.run))
    graph.add_node("export", trace_node("export")(format_exporter.run))

    graph.set_entry_point("outline")

    # outline → Send() 扇出：fan_out_sections 返回 [Send("section_writer", ...), ...]
    # 或 [Send("diagram", state)]（无未写章节时）
    graph.add_conditional_edges(
        "outline",
        fan_out_sections,
        ["section_writer", "diagram"],
    )

    # Fan-in：所有并行 writer 完成后才进入 diagram
    graph.add_edge("section_writer", "diagram")
    graph.add_edge("diagram", "code_scaffold")
    graph.add_edge("code_scaffold", "consistency")
    graph.add_edge("consistency", "revision")
    graph.add_edge("revision", "assemble")
    graph.add_edge("assemble", "export")
    graph.add_edge("export", END)

    return graph


generation_graph = build_generation_graph().compile()
