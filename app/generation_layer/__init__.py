"""C3 — Generation Layer（生成层）。

基于 PlanningResult 生成技术方案文档（Markdown），
含模板系统、Mermaid 图表、代码框架、多格式导出。
"""

from app.generation_layer.agent_graph import build_generation_graph, generation_graph

__all__ = ["build_generation_graph", "generation_graph"]
