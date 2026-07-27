"""回放播放器 — 按时间线重演 Agent 的决策过程。"""

from __future__ import annotations

import json

from app.observability.replay.models import DecisionRecord, TraceTree
from app.observability.replay.recorder import ReplayStorage


class StepNotFoundError(Exception):
    """步骤不存在异常。"""

    def __init__(self, task_id: str, step_index: int) -> None:
        self.task_id = task_id
        self.step_index = step_index
        super().__init__(f"任务 {task_id} 的第 {step_index} 步不存在")


class ReplayPlayer:
    """回放播放器 — 按时间线重演 Agent 的决策过程。"""

    def __init__(self, storage: ReplayStorage | None = None) -> None:
        """初始化回放播放器。

        Args:
            storage: ReplayStorage 实例。
        """
        self.storage = storage or ReplayStorage()

    async def get_trace(self, task_id: str) -> TraceTree | None:
        """获取任务的完整决策链。

        Args:
            task_id: 任务 ID。

        Returns:
            TraceTree 实例。
        """
        return await self.storage.get_trace(task_id)

    async def replay_step(self, task_id: str, step_index: int) -> DecisionRecord:
        """回放单步决策。

        Args:
            task_id: 任务 ID。
            step_index: 步骤索引（从 0 开始）。

        Returns:
            该步骤的 DecisionRecord。

        Raises:
            StepNotFoundError: 步骤不存在。
        """
        trace = await self.get_trace(task_id)
        if not trace or step_index >= len(trace.nodes):
            raise StepNotFoundError(task_id, step_index)
        return trace.nodes[step_index]

    async def export_replay(self, task_id: str, fmt: str = "markdown") -> str:
        """导出回放报告（用于复盘）。

        Args:
            task_id: 任务 ID。
            fmt: 导出格式（markdown / json）。

        Returns:
            格式化的回放报告。
        """
        trace = await self.get_trace(task_id)
        if not trace:
            return ""

        if fmt == "json":
            return trace.model_dump_json(indent=2)
        return self._to_markdown(trace)

    @staticmethod
    def _to_markdown(trace: TraceTree) -> str:
        """导出 Markdown 格式的回放报告。"""
        lines = [
            "# Agent 行为回放报告",
            "",
            f"**任务 ID**: {trace.task_id}",
            f"**开始时间**: {trace.start_time.isoformat()}",
            f"**结束时间**: {trace.end_time.isoformat() if trace.end_time else '进行中'}",
            f"**总耗时**: {trace.total_duration_ms:.0f}ms",
            f"**决策步数**: {len(trace.nodes)}",
            "",
            "---",
            "",
        ]
        for i, node in enumerate(trace.nodes):
            lines.extend([
                f"## 第 {i + 1} 步：{node.agent_name}.{node.node_name}",
                "",
                f"**耗时**: {node.duration_ms:.0f}ms | **Token**: {node.tokens_consumed}",
                f"**摘要**: {node.decision_summary}",
                "",
                "### LLM 输入（截取）",
                "```",
                f"{node.input_prompt[:500]}",
                "```",
                "",
                "### LLM 输出",
                "```",
                f"{node.llm_response[:500]}",
                "```",
                "",
            ])
            if node.tool_calls:
                lines.extend([
                    "### 工具调用",
                    "```json",
                    json.dumps(node.tool_calls, indent=2, ensure_ascii=False),
                    "```",
                    "",
                ])
            lines.append("---")
            lines.append("")

        return "\n".join(lines)
