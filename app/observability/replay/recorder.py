"""决策记录器 — 记录 Agent 每一步的完整决策过程。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.logger import get_logger
from app.observability.replay.models import DecisionRecord, TraceTree

logger = get_logger("prd2tsd.replay.recorder")


class ReplayStorage:
    """回放存储 — 内存实现。"""

    def __init__(self) -> None:
        self._records: dict[str, DecisionRecord] = {}
        self._traces: dict[str, TraceTree] = {}

    async def save(self, record: DecisionRecord) -> None:
        self._records[record.id] = record

    async def save_trace(self, trace: TraceTree) -> None:
        self._traces[trace.task_id] = trace

    async def get_trace(self, task_id: str) -> TraceTree | None:
        return self._traces.get(task_id)

    async def get_record(self, record_id: str) -> DecisionRecord | None:
        return self._records.get(record_id)


class DecisionRecorder:
    """决策记录器 — 记录 Agent 每一步的完整决策过程。

    记录内容：
    - LLM 输入（完整 Prompt）
    - LLM 输出（原始响应 + Tool Calls）
    - State 变化（执行前后的 diff）
    - 性能数据（耗时、Token 消耗）
    """

    def __init__(self, storage: ReplayStorage | None = None) -> None:
        """初始化决策记录器。

        Args:
            storage: ReplayStorage 实例。
        """
        self.storage = storage or ReplayStorage()
        self._current_trace: dict[str, TraceTree] = {}

    async def start_trace(self, task_id: str) -> None:
        """开始追踪一个新任务。

        Args:
            task_id: 任务 ID。
        """
        self._current_trace[task_id] = TraceTree(
            task_id=task_id,
            start_time=datetime.now(UTC),
        )
        logger.info("开始追踪: task=%s", task_id)

    async def record_decision(
        self,
        task_id: str,
        agent_name: str,
        node_name: str,
        input_state: dict[str, Any],
        input_prompt: str,
        input_tools: list[dict],
        llm_response: str,
        tool_calls: list[dict],
        tool_results: list[dict],
        output_state: dict[str, Any],
        duration_ms: float,
        tokens: int,
    ) -> DecisionRecord:
        """记录一次 Node 执行。

        Args:
            task_id: 任务 ID。
            agent_name: Agent 名称。
            node_name: Node 名称。
            input_state: 输入 State。
            input_prompt: 输入 Prompt。
            input_tools: 可用工具。
            llm_response: LLM 原始响应。
            tool_calls: LLM 选择的工具。
            tool_results: 工具执行结果。
            output_state: 输出 State。
            duration_ms: 耗时（毫秒）。
            tokens: Token 消耗。

        Returns:
            创建的 DecisionRecord。
        """
        record = DecisionRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            trace_id=task_id,
            agent_name=agent_name,
            node_name=node_name,
            input_state_snapshot=self._summarize_state(input_state),
            input_prompt=self._truncate_prompt(input_prompt),
            input_tools=input_tools,
            llm_response=llm_response,
            tool_calls=tool_calls,
            tool_results=tool_results,
            output_state_diff=self._compute_diff(input_state, output_state),
            duration_ms=duration_ms,
            tokens_consumed=tokens,
        )

        # 追加到追踪树
        trace = self._current_trace.get(task_id)
        if trace:
            trace.nodes.append(record)
            if len(trace.nodes) > 1:
                prev = trace.nodes[-2]
                trace.edges.append((prev.id, record.id, agent_name))
                # 异步生成决策摘要
                asyncio.create_task(self._summarize_decision(record))

        await self.storage.save(record)
        return record

    async def end_trace(self, task_id: str) -> TraceTree | None:
        """结束追踪并保存完整链路。

        Args:
            task_id: 任务 ID。

        Returns:
            完成的 TraceTree。
        """
        trace = self._current_trace.pop(task_id, None)
        if trace:
            trace.end_time = datetime.now(UTC)
            trace.total_duration_ms = (
                trace.end_time - trace.start_time
            ).total_seconds() * 1000
            await self.storage.save_trace(trace)
            logger.info("追踪完成: task=%s, steps=%d, duration=%.0fms",
                        task_id, len(trace.nodes), trace.total_duration_ms)
        return trace

    @staticmethod
    def _compute_diff(before: dict, after: dict) -> dict[str, Any]:
        """计算 State 的变化（只保留变化字段）。"""
        diff: dict[str, Any] = {}
        for key in after:
            if key not in before or before[key] != after[key]:
                val = after[key]
                if isinstance(val, (list, dict)):
                    diff[key] = {"type": type(val).__name__, "size": len(val), "changed": True}
                else:
                    diff[key] = val
        return diff

    @staticmethod
    def _truncate_prompt(prompt: str, max_len: int = 2000) -> str:
        """截断过长的 Prompt。"""
        if len(prompt) <= max_len:
            return prompt
        half = max_len // 2
        return prompt[:half] + "\n...(中间省略)...\n" + prompt[-half:]

    @staticmethod
    def _summarize_state(state: dict) -> dict[str, Any]:
        """摘要化 State。"""
        summary: dict[str, Any] = {}
        for key, val in state.items():
            if isinstance(val, str) and len(val) > 200:
                summary[key] = val[:200] + "..."
            elif isinstance(val, list):
                summary[key] = f"[{type(val).__name__}:{len(val)}]"
            else:
                summary[key] = val
        return summary

    async def _summarize_decision(self, record: DecisionRecord) -> None:
        """用 LLM 生成人类可读的决策摘要。"""
        try:
            from app.llm_gateway import gateway

            prompt = f"""总结以下 Agent 决策过程（一句话）：
Agent: {record.agent_name}
Node: {record.node_name}
LLM 输入: {record.input_prompt[:200]}
LLM 输出: {record.llm_response[:200]}
调用的工具: {[tc.get('function', {}).get('name', '') for tc in record.tool_calls]}
"""
            resp = await gateway.complete(
                prompt=prompt,
                task_type="decision_summary",
                max_tokens=100,
            )
            record.decision_summary = resp.content
        except Exception:
            record.decision_summary = f"{record.agent_name}.{record.node_name}"
