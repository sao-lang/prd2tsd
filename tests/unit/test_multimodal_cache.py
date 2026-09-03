"""Gateway 多模态缓存身份测试。"""

from app.llm_gateway import LLMGateway


def test_image_payload_is_part_of_exact_cache_identity() -> None:
    """相同 OCR Prompt 配不同图片时不得共享缓存键。"""
    first, first_is_multimodal = LLMGateway._cache_prompt(
        "OCR",
        [{"url": "data:image/png;base64,AAAA"}],
    )
    same, _ = LLMGateway._cache_prompt("OCR", [{"url": "data:image/png;base64,AAAA"}])
    second, second_is_multimodal = LLMGateway._cache_prompt(
        "OCR",
        [{"url": "data:image/png;base64,BBBB"}],
    )

    assert first_is_multimodal is True
    assert second_is_multimodal is True
    assert first == same
    assert first != second
    assert "AAAA" not in first


def test_text_cache_identity_is_unchanged() -> None:
    """纯文本调用继续使用原 Prompt 参与语义缓存。"""
    cache_prompt, is_multimodal = LLMGateway._cache_prompt("hello", None)

    assert cache_prompt == "hello"
    assert is_multimodal is False
