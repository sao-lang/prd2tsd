"""Agent 行为回放单元测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.observability.replay.models import DecisionRecord, TraceTree
from app.observability.replay.player import ReplayPlayer
from app.observability.replay.recorder import DecisionRecorder, ReplayStorage


class TestReplayStorage:
    """回放存储单元测试。"""

    @pytest.fixture
    def storage(self) -> ReplayStorage:
        return ReplayStorage()

    @pytest.mark.asyncio
    async def test_save_and_get_record(self, storage: ReplayStorage) -> None:
        """验证保存和获取决策记录。"""
        record = DecisionRecord(
            id="rec-1",
            task_id="task-1",
            trace_id="trace-1",
            agent_name="analysis",
            node_name="requirement_extractor",
        )
        await storage.save(record)
        retrieved = await storage.get_record("rec-1")
        assert retrieved is not None
        assert retrieved.id == "rec-1"
        assert retrieved.agent_name == "analysis"

    @pytest.mark.asyncio
    async def test_save_and_get_trace(self, storage: ReplayStorage) -> None:
        """验证保存和获取追踪树。"""
        trace = TraceTree(
            task_id="task-1",
            start_time=datetime.now(UTC),
        )
        await storage.save_trace(trace)
        retrieved = await storage.get_trace("task-1")
        assert retrieved is not None
        assert retrieved.task_id == "task-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_record(self, storage: ReplayStorage) -> None:
        """验证获取不存在的记录返回 None。"""
        record = await storage.get_record("not-exist")
        assert record is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_trace(self, storage: ReplayStorage) -> None:
        """验证获取不存在的追踪返回 None。"""
        trace = await storage.get_trace("not-exist")
        assert trace is None


class TestDecisionRecorder:
    """决策记录器单元测试。"""

    @pytest.fixture
    def recorder(self) -> DecisionRecorder:
        return DecisionRecorder()

    @pytest.mark.asyncio
    async def test_start_trace(self, recorder: DecisionRecorder) -> None:
        """验证开始追踪。"""
        await recorder.start_trace("task-1")
        assert "task-1" in recorder._current_trace

    @pytest.mark.asyncio
    async def test_record_decision(self, recorder: DecisionRecorder) -> None:
        """验证记录决策。"""
        await recorder.start_trace("task-1")
        record = await recorder.record_decision(
            task_id="task-1",
            agent_name="analysis",
            node_name="extractor",
            input_state={"prd_raw": "test"},
            input_prompt="分析需求",
            input_tools=[],
            llm_response='{"requirements": []}',
            tool_calls=[],
            tool_results=[],
            output_state={"requirements": []},
            duration_ms=100.0,
            tokens=50,
        )
        assert record is not None
        assert record.agent_name == "analysis"
        assert record.duration_ms == 100.0
        assert record.tokens_consumed == 50

    @pytest.mark.asyncio
    async def test_end_trace(self, recorder: DecisionRecorder) -> None:
        """验证结束追踪。"""
        await recorder.start_trace("task-1")
        await recorder.record_decision(
            task_id="task-1",
            agent_name="analysis",
            node_name="extractor",
            input_state={},
            input_prompt="test",
            input_tools=[],
            llm_response="",
            tool_calls=[],
            tool_results=[],
            output_state={},
            duration_ms=50.0,
            tokens=10,
        )
        trace = await recorder.end_trace("task-1")
        assert trace is not None
        assert trace.task_id == "task-1"
        assert trace.end_time is not None
        assert len(trace.nodes) == 1

    @pytest.mark.asyncio
    async def test_compute_diff(self, recorder: DecisionRecorder) -> None:
        """验证 State diff 计算。"""
        before = {"a": 1, "b": "old"}
        after = {"a": 1, "b": "new", "c": "added"}
        diff = DecisionRecorder._compute_diff(before, after)
        assert "b" in diff  # 变化
        assert "a" not in diff  # 未变化
        assert "c" in diff  # 新增

    def test_truncate_prompt_short(self) -> None:
        """验证短 Prompt 不截断。"""
        result = DecisionRecorder._truncate_prompt("短文本", max_len=100)
        assert result == "短文本"

    def test_truncate_prompt_long(self) -> None:
        """验证长 Prompt 截断。"""
        long_text = "a" * 2000
        result = DecisionRecorder._truncate_prompt(long_text, max_len=100)
        assert len(result) <= 200  # 前后各50 + 省略标记
        assert "...(中间省略)..." in result

    def test_summarize_state_long_string(self) -> None:
        """验证长字符串被摘要。"""
        state = {"long": "a" * 500}
        summary = DecisionRecorder._summarize_state(state)
        assert len(summary["long"]) < 300
        assert summary["long"].endswith("...")

    def test_summarize_state_list(self) -> None:
        """验证列表被摘要为大小信息。"""
        state = {"items": [1, 2, 3]}
        summary = DecisionRecorder._summarize_state(state)
        assert "list" in summary["items"]
        assert "3" in summary["items"]


class TestReplayPlayer:
    """回放播放器单元测试。"""

    @pytest.fixture
    def player(self) -> ReplayPlayer:
        return ReplayPlayer()

    @pytest.mark.asyncio
    async def test_export_replay_markdown(self) -> None:
        """验证导出 Markdown 回放报告。"""
        # 创建带数据的存储
        storage = ReplayStorage()
        trace = TraceTree(
            task_id="task-1",
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC),
            total_duration_ms=150.0,
        )
        record = DecisionRecord(
            id="rec-1",
            task_id="task-1",
            trace_id="trace-1",
            agent_name="analysis",
            node_name="extractor",
            decision_summary="提取了5个需求",
        )
        trace.nodes.append(record)
        await storage.save(record)
        await storage.save_trace(trace)

        # 使用绑定了 storage 的 player
        player = ReplayPlayer(storage=storage)
        report = await player.export_replay("task-1", fmt="markdown")
        assert report is not None
        assert "# Agent 行为回放报告" in report
        assert "analysis.extractor" in report
        assert "提取了5个需求" in report

    @pytest.mark.asyncio
    async def test_export_replay_empty(self, player: ReplayPlayer) -> None:
        """验证导出不存在的回放返回空字符串。"""
        report = await player.export_replay("not-exist")
        assert report == ""
