"""数据脱敏单元测试 — 各类型敏感数据检测。"""

from __future__ import annotations

from app.security.data_masking import DataMaskingEngine


def test_mask_api_key():
    """验证 API Key 被正确脱敏。"""
    engine = DataMaskingEngine()
    result = engine.mask("sk-abc123def456", level="L3")
    assert "[MASKED_API_KEY]" in result
    assert "sk-abc" not in result


def test_mask_email():
    """验证邮箱被脱敏。"""
    engine = DataMaskingEngine()
    result = engine.mask("联系邮箱: user@example.com")
    assert "[MASKED_EMAIL]" in result


def test_mask_by_level():
    """验证不同安全等级脱敏范围不同。"""
    engine = DataMaskingEngine()
    text = "password: pass123, 邮箱: a@b.com, 公网IP: 8.8.8.8"
    l1 = engine.mask(text, level="L1")
    l2 = engine.mask(text, level="L2")
    # L1 脱敏邮箱和 IP，但不脱敏密码
    assert "[MASKED_EMAIL]" in l1
    assert "[MASKED_IP_ADDRESS]" in l1
    # L2 额外脱敏密码
    assert "[MASKED_PASSWORD]" in l2


def test_mask_empty_text():
    """验证空文本。"""
    engine = DataMaskingEngine()
    assert engine.mask("") == ""


def test_no_sensitive_data():
    """验证无敏感数据时不修改。"""
    engine = DataMaskingEngine()
    text = "这是一段普通文本，没有敏感信息。"
    assert engine.mask(text) == text


def test_mask_multiple_types():
    """验证多种敏感数据同时脱敏。"""
    engine = DataMaskingEngine()
    text = "API Key: sk-abc123def456, 邮箱: test@example.com"
    result = engine.mask(text, level="L3")
    assert "[MASKED_API_KEY]" in result
    assert "[MASKED_EMAIL]" in result


def test_mask_with_details():
    """验证脱敏详情返回。"""
    engine = DataMaskingEngine()
    result = engine.mask_with_details("sk-abc123def456和user@test.com", level="L3")
    assert result["masked_text"] is not None
    assert len(result["masked_types"]) > 0
