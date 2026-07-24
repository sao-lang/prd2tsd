"""观测性模块单元测试。"""

from __future__ import annotations

from app.observability.metrics import (
    LLM_CALL_TOTAL,
    LLM_COST_TOTAL,
    LLM_TOKEN_USAGE,
    track_llm_call,
)


def test_llm_call_metrics_labels() -> None:
    """验证 LLM 调用指标标签设置。"""
    LLM_CALL_TOTAL.labels(model="deepseek-chat", layer="analysis", node="extractor").inc()
    val = LLM_CALL_TOTAL.labels(model="deepseek-chat", layer="analysis", node="extractor")._value.get()
    assert val == 1.0


def test_llm_cost_metrics() -> None:
    """验证成本指标。"""
    LLM_COST_TOTAL.labels(model="gpt-4o-mini").inc(0.5)
    LLM_COST_TOTAL.labels(model="gpt-4o-mini").inc(0.3)
    val = LLM_COST_TOTAL.labels(model="gpt-4o-mini")._value.get()
    assert val == 0.8


def test_llm_token_usage() -> None:
    """验证 Token 消耗指标。"""
    LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="input").inc(150)
    LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="output").inc(50)
    input_val = LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="input")._value.get()
    output_val = LLM_TOKEN_USAGE.labels(model="deepseek-chat", type="output")._value.get()
    assert input_val == 150
    assert output_val == 50


def test_track_llm_call_context_manager() -> None:
    """验证 LLM 调用追踪上下文管理器。"""
    with track_llm_call(model="deepseek-chat", layer="test", node="test_node") as info:
        info["input_tokens"] = 100
        info["output_tokens"] = 50

    # 验证指标已记录
    call_val = LLM_CALL_TOTAL.labels(
        model="deepseek-chat", layer="test", node="test_node",
    )._value.get()
    assert call_val >= 1.0
