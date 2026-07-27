"""意图分类器 — 自动判断用户输入的任务类型。

两级策略：
1. 规则匹配（关键词 + 模式）— 快路径，无需 LLM
2. LLM 分类（规则不确定时）— 准确路径，调用轻量模型
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum

from app.llm_gateway import LLMGateway


class IntentType(StrEnum):
    """任务意图类型。"""

    CHAT = "chat"  # 纯对话（闲聊、问候、普通交流）
    KNOWLEDGE_QA = "knowledge_qa"  # 知识查询（查文档、问概念、搜代码）
    COMPLEX_GENERATION = "complex_generation"  # 复杂生成（PRD→TSD、技术方案）
    CLARIFICATION = "clarification"  # 需要更多信息（歧义输入）


@dataclass
class IntentResult:
    """意图分类结果。"""

    intent: IntentType
    confidence: float  # 置信度 0.0 ~ 1.0
    sub_intent: str = ""
    params: dict = field(default_factory=dict)
    explanation: str = ""


class IntentClassifier:
    """意图分类器 — 自动判断用户输入的任务类型。

    两级策略：
    1. 规则匹配（关键词 + 模式）— 快路径，无需 LLM
    2. LLM 分类（规则不确定时）— 准确路径，调用轻量模型
    """

    def __init__(self, llm_gateway: LLMGateway | None = None) -> None:
        """初始化意图分类器。

        Args:
            llm_gateway: LLM Gateway 实例（可选，用于 LLM 分类）。
        """
        self._llm_gateway = llm_gateway

    # ── 规则层 ──

    CHAT_PATTERNS = [
        "你好",
        "嗨",
        "hello",
        "hi",
        "hey",
        "再见",
        "拜拜",
        "bye",
        "谢谢",
        "感谢",
        "thanks",
        "thank you",
    ]

    KNOWLEDGE_PATTERNS = [
        "是什么",
        "什么是",
        "有哪些",
        "哪个",
        "怎么",
        "如何",
        "怎样",
        "有没有",
        "是否存在",
        "解释一下",
        "说明一下",
        "what is",
        "how to",
        "how do",
        "search",
        "find",
        "look up",
        "文档",
        "文件",
        "知识库",
        "知识图谱",
    ]

    GENERATION_PATTERNS = [
        "生成",
        "创建",
        "编写",
        "撰写",
        "设计",
        "设计方案",
        "技术方案",
        "写文档",
        "生成文档",
        "generate",
        "create",
        "design",
        "技术规格",
        "TSD",
        "PRD",
    ]

    async def classify(
        self,
        user_input: str,
        session_history: list[dict] | None = None,
    ) -> IntentResult:
        """分类用户输入。

        Args:
            user_input: 用户输入文本。
            session_history: 当前会话历史（可选，用于上下文判断）。

        Returns:
            意图分类结果。
        """
        input_lower = user_input.lower().strip()

        # Stage 1: 规则匹配（快路径）
        rule_result = self._rule_based(input_lower)
        if rule_result and rule_result.confidence >= 0.8:
            return rule_result

        # Stage 2: LLM 分类（规则不确定时）
        if self._llm_gateway:
            llm_result = await self._llm_classify(user_input, session_history)
            if llm_result.confidence > (rule_result.confidence if rule_result else 0.5):
                return llm_result

        return rule_result or IntentResult(
            intent=IntentType.COMPLEX_GENERATION,
            confidence=0.5,
            explanation="规则和 LLM 均无法确定，默认走复杂生成",
        )

    def _rule_based(self, input_lower: str) -> IntentResult | None:
        """基于规则的快速分类。"""
        # 检查生成模式（最高优先级）
        for pattern in self.GENERATION_PATTERNS:
            if pattern in input_lower:
                return IntentResult(
                    intent=IntentType.COMPLEX_GENERATION,
                    confidence=0.85,
                    sub_intent="pattern_generation",
                    explanation=f"匹配生成关键词: {pattern}",
                )

        # 检查知识查询模式
        knowledge_match_count = sum(1 for p in self.KNOWLEDGE_PATTERNS if p in input_lower)
        if knowledge_match_count >= 2:
            return IntentResult(
                intent=IntentType.KNOWLEDGE_QA,
                confidence=0.9,
                sub_intent="multi_pattern_qa",
                explanation=f"匹配 {knowledge_match_count} 个知识查询关键词",
            )
        if knowledge_match_count == 1:
            return IntentResult(
                intent=IntentType.KNOWLEDGE_QA,
                confidence=0.7,
                sub_intent="single_pattern_qa",
                explanation="匹配 1 个知识查询关键词",
            )

        # 检查闲聊模式
        for pattern in self.CHAT_PATTERNS:
            if pattern in input_lower:
                return IntentResult(
                    intent=IntentType.CHAT,
                    confidence=0.8,
                    explanation=f"匹配闲聊关键词: {pattern}",
                )

        # 短查询（< 8 字）倾向于知识查询
        if len(input_lower) < 8:
            return IntentResult(
                intent=IntentType.KNOWLEDGE_QA,
                confidence=0.6,
                sub_intent="short_query",
                explanation="短查询，倾向于知识检索",
            )

        return None

    async def _llm_classify(
        self,
        user_input: str,
        session_history: list[dict] | None = None,
    ) -> IntentResult:
        """使用 LLM 进行意图分类。"""
        if not self._llm_gateway:
            return IntentResult(intent=IntentType.COMPLEX_GENERATION, confidence=0.5)

        history_context = ""
        if session_history:
            recent = session_history[-3:]
            history_context = "最近对话：\n" + "\n".join(
                f"{m.get('role', '')}: {m.get('content', '')[:200]}" for m in recent
            )

        prompt = f"""分析用户输入的任务类型，只返回 JSON：

{history_context}

用户输入：{user_input}

可选类型：
1. chat — 纯对话（问候、闲聊、感谢、简单交流）
2. knowledge_qa — 知识查询（查找文档、问概念、技术问题）
3. complex_generation — 复杂生成（生成文档、设计方案、技术方案）
4. clarification — 需要澄清（输入模糊、歧义）

返回格式：
{{"intent": "类型名", "confidence": 0.0~1.0, "reason": "判断理由"}}
"""
        try:
            resp = await self._llm_gateway.complete(
                prompt=prompt,
                task_type="intent_classify",
                temperature=0.1,
                max_tokens=200,
            )
            data = json.loads(resp.content)
            intent_str = data.get("intent", "complex_generation")
            try:
                intent = IntentType(intent_str)
            except ValueError:
                intent = IntentType.COMPLEX_GENERATION

            return IntentResult(
                intent=intent,
                confidence=float(data.get("confidence", 0.7)),
                explanation=data.get("reason", ""),
            )
        except Exception:
            return IntentResult(
                intent=IntentType.COMPLEX_GENERATION,
                confidence=0.5,
                explanation="LLM 分类失败，默认走复杂生成",
            )
