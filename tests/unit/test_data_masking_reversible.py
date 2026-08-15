"""数据脱敏可逆掩码回归测试。"""

from __future__ import annotations

from app.security.data_masking import DataMaskingEngine


def test_mask_reversible_roundtrip() -> None:
    """敏感信息掩码后进入 LLM，输出可还原为原文。"""
    engine = DataMaskingEngine()
    original = "请调用 sk-abc123def456 连接服务，邮箱 admin@example.com"
    masked = engine.mask_reversible(original, level="L3")

    assert "sk-abc123def456" not in masked
    assert "MASKED" in masked
    assert engine.unmask(masked) == original
