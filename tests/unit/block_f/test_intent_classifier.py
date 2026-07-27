"""IntentClassifier 单元测试。"""

from __future__ import annotations

import pytest

from app.orchestrator.intent_classifier import IntentClassifier, IntentType


class TestIntentClassifier:
    """IntentClassifier 测试。"""

    def setup_method(self):
        self.classifier = IntentClassifier()

    @pytest.mark.asyncio
    async def test_chat_greeting(self):
        """测试问候语识别为 CHAT。"""
        result = await self.classifier.classify("你好")
        assert result.intent == IntentType.CHAT
        assert result.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_chat_english_greeting(self):
        """测试英文问候。"""
        result = await self.classifier.classify("hello")
        assert result.intent == IntentType.CHAT

    @pytest.mark.asyncio
    async def test_chat_thanks(self):
        """测试感谢。"""
        result = await self.classifier.classify("谢谢")
        assert result.intent == IntentType.CHAT

    @pytest.mark.asyncio
    async def test_knowledge_qa_multi_pattern(self):
        """测试多模式知识查询。"""
        result = await self.classifier.classify("什么是微服务")
        assert result.intent == IntentType.KNOWLEDGE_QA
        # "什么" 和 "是" 不在知识模式中... 实际上需要看匹配模式
        # "什么是" - "什么" is in KNOWLEDGE_PATTERNS? No. Let me check - "是什么" is in there
        # Actually "是什么" is a pattern, "什么是" contains "是什么" as substring? No.
        # "什么是" - the pattern is "是什么" which is not exactly matched.
        # Let me try a better query
        pass

    @pytest.mark.asyncio
    async def test_knowledge_qa_explicit(self):
        """测试显式知识查询。"""
        result = await self.classifier.classify("解释一下微服务架构有哪些组件")
        assert result.intent == IntentType.KNOWLEDGE_QA

    @pytest.mark.asyncio
    async def test_knowledge_qa_how_to(self):
        """测试 How-to 问题。"""
        result = await self.classifier.classify("如何部署微服务")
        assert result.intent == IntentType.KNOWLEDGE_QA

    @pytest.mark.asyncio
    async def test_generation_prd(self):
        """测试 PRD 生成。"""
        result = await self.classifier.classify("生成完整的技术方案文档")
        assert result.intent == IntentType.COMPLEX_GENERATION
        assert result.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_generation_design(self):
        """测试设计文档生成。"""
        result = await self.classifier.classify("帮我设计一个电商系统架构")
        assert result.intent == IntentType.COMPLEX_GENERATION

    @pytest.mark.asyncio
    async def test_short_query_defaults_to_qa(self):
        """测试短查询默认走知识查询。"""
        result = await self.classifier.classify("test")
        assert result.intent == IntentType.KNOWLEDGE_QA
        assert result.confidence == 0.6

    @pytest.mark.asyncio
    async def test_fallback_to_generation(self):
        """测试无法判断时默认走复杂生成。"""
        # 一个不匹配任何模式的长文本
        result = await self.classifier.classify("这是一个很长的不匹配任何模式的测试文本内容")
        # 没有 LLM gateway 时，规则无法判断，返回 None → 默认 complex_generation
        assert result.intent == IntentType.COMPLEX_GENERATION
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_multiple_generation_keywords(self):
        """测试多个生成关键词。"""
        result = await self.classifier.classify("请生成设计文档并编写技术方案")
        assert result.intent == IntentType.COMPLEX_GENERATION
