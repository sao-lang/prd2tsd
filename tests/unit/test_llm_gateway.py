"""LLM Gateway 单元测试 — 配置解析/成本/缓存。"""

from __future__ import annotations

from app.llm_gateway import config_manager
from app.llm_gateway.cache import SemanticCache
from app.llm_gateway.cost_tracker import CostTracker


def test_gateway_config_resolution():
    """验证 Gateway 通过 ModelConfigManager 解析模型配置。"""
    config, model = config_manager.resolve_model("analysis.requirement")
    assert config is not None
    assert model is not None


def test_gateway_dynamic_config_takes_effect():
    """验证运行时修改配置后生效。"""
    config_manager.update_config(
        "llm", "deepseek",
        {"base_url": "https://custom.deepseek.com/v1"},
    )
    config, model = config_manager.resolve_model("analysis.requirement")
    assert "custom.deepseek.com" in config.base_url
    # 恢复
    config_manager.reset_to_env()


def test_cost_tracker():
    """验证成本追踪器。"""
    tracker = CostTracker()
    tracker.record("deepseek-chat", input_tokens=100, output_tokens=50)
    tracker.record("gpt-4o-mini", input_tokens=200, output_tokens=100)

    total_cost = tracker.get_total_cost()
    total_tokens = tracker.get_total_tokens()
    assert total_cost > 0
    assert total_tokens == 450
    assert len(tracker.get_records()) == 2


def test_cost_tracker_clear():
    """验证成本追踪器清除。"""
    tracker = CostTracker()
    tracker.record("deepseek-chat", input_tokens=10, output_tokens=5)
    tracker.clear()
    assert tracker.get_total_cost() == 0.0
    assert tracker.get_total_tokens() == 0


def test_semantic_cache():
    """验证语义缓存。"""
    cache = SemanticCache(ttl=3600, max_size=100)
    key = cache.make_key("Hello", "test")
    assert cache.get(key) is None

    cache.set(key, "Hello World")
    assert cache.get(key) == "Hello World"


def test_semantic_cache_clear():
    """验证语义缓存清除。"""
    cache = SemanticCache()
    key = cache.make_key("test", "test")
    cache.set(key, "value")
    assert cache.size == 1
    cache.clear()
    assert cache.size == 0


def test_cache_max_size():
    """验证缓存最大容量限制。"""
    cache = SemanticCache(ttl=3600, max_size=3)
    for i in range(5):
        key = cache.make_key(f"prompt-{i}", "test")
        cache.set(key, f"content-{i}")
    assert cache.size <= 3


def test_cache_invalidate():
    """验证缓存失效。"""
    cache = SemanticCache()
    key = cache.make_key("test-key", "test")
    cache.set(key, "value")
    assert cache.get(key) is not None
    cache.invalidate(key)
    assert cache.get(key) is None
