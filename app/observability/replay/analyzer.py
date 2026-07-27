"""决策分析器 — 分析 Agent 决策模式和性能。"""

from __future__ import annotations

from typing import Any

from app.observability.replay.models import TraceTree


class DecisionAnalyzer:
    """决策分析器 — 分析 Agent 决策模式和性能。"""

    async def analyze_trace(self, trace: TraceTree) -> dict[str, Any]:
        """分析完整追踪链路。

        Args:
            trace: TraceTree 实例。

        Returns:
            分析结果。
        """
        if not trace.nodes:
            return {"status": "empty"}

        total_steps = len(trace.nodes)
        total_duration = trace.total_duration_ms
        total_tokens = sum(n.tokens_consumed for n in trace.nodes)

        # 按 Agent 分组统计
        agent_stats: dict[str, dict[str, float | int]] = {}
        for node in trace.nodes:
            if node.agent_name not in agent_stats:
                agent_stats[node.agent_name] = {"calls": 0, "duration_ms": 0.0, "tokens": 0}
            agent_stats[node.agent_name]["calls"] += 1  # type: ignore[operator]
            agent_stats[node.agent_name]["duration_ms"] += node.duration_ms  # type: ignore[operator]
            agent_stats[node.agent_name]["tokens"] += node.tokens_consumed  # type: ignore[operator]

        # 耗时最长的节点
        sorted_by_duration = sorted(trace.nodes, key=lambda n: n.duration_ms, reverse=True)

        return {
            "status": "completed",
            "total_steps": total_steps,
            "total_duration_ms": total_duration,
            "total_tokens": total_tokens,
            "avg_step_duration_ms": total_duration / max(total_steps, 1),
            "agent_stats": agent_stats,
            "top_slowest_nodes": [
                {
                    "step": i + 1,
                    "agent": n.agent_name,
                    "node": n.node_name,
                    "duration_ms": n.duration_ms,
                    "tokens": n.tokens_consumed,
                    "summary": n.decision_summary,
                }
                for i, n in enumerate(sorted_by_duration[:5])
            ],
            "has_tool_calls": any(n.tool_calls for n in trace.nodes),
            "has_errors": any("error" in n.output_state_diff for n in trace.nodes),
        }
