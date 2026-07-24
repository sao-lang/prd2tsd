"""C3 — Generation Layer LangGraph StateGraph。"""

from __future__ import annotations

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

outline_node = OutlineGeneratorNode()
section_writer = SectionWriterNode()
diagram_generator = DiagramGeneratorNode()
code_scaffold = CodeScaffoldGeneratorNode()
consistency_checker = ConsistencyCheckerNode()
revision_node = RevisionNode()
format_assembler = FormatAssemblerNode()
format_exporter = FormatExporterNode()


def build_generation_graph() -> StateGraph:
    """构建并编译 Generation Layer StateGraph。

    C3 链路：
    Outline → SectionWriter → DiagramGenerator → CodeScaffold
    → ConsistencyChecker → Revision → FormatAssembler → FormatExporter

    Returns:
        编译后的 StateGraph。
    """
    graph = StateGraph(GenerationState)

    graph.add_node("outline", outline_node.run)
    graph.add_node("section_writer", section_writer.run)
    graph.add_node("diagram", diagram_generator.run)
    graph.add_node("code_scaffold", code_scaffold.run)
    graph.add_node("consistency", consistency_checker.run)
    graph.add_node("revision", revision_node.run)
    graph.add_node("assemble", format_assembler.run)
    graph.add_node("export", format_exporter.run)

    graph.set_entry_point("outline")
    graph.add_edge("outline", "section_writer")
    graph.add_edge("section_writer", "diagram")
    graph.add_edge("diagram", "code_scaffold")
    graph.add_edge("code_scaffold", "consistency")
    graph.add_edge("consistency", "revision")
    graph.add_edge("revision", "assemble")
    graph.add_edge("assemble", "export")
    graph.add_edge("export", END)

    return graph


generation_graph = build_generation_graph().compile()
