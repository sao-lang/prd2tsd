"""GatewayChatModel — 将 LLM Gateway 包装为 LangChain BaseChatModel。

保留 Gateway 的成本追踪、速率限制、熔断、护栏等功能，
同时提供 LangChain 的标准接口（ainvoke / astream / bind_tools 等）。

使用方式：
    from app.llm_gateway.langchain_adapter import GatewayChatModel
    llm = GatewayChatModel(gateway=gateway, task_type="analysis", layer="analysis")
    chain = prompt | llm | parser
    result = await chain.ainvoke({"input": "..."})
"""

from __future__ import annotations

from typing import Any, Iterator

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.core.logger import get_logger

logger = get_logger("prd2tsd.langchain_adapter")


class GatewayChatModel(BaseChatModel):
    """将 LLM Gateway 包装为 LangChain BaseChatModel。

    保留 Gateway 的成本追踪、速率限制、熔断、护栏等功能，
    同时提供 LangChain 的标准接口。

    Attributes:
        gateway: LLM Gateway 实例。
        default_model: 默认模型名。
        task_type: 任务类型（用于 Gateway 路由/计费）。
        layer: 所属层（analysis/planning/generation/evaluation）。
        node: 所属节点名。
    """

    gateway: Any
    default_model: str = "deepseek-chat"
    task_type: str = "default"
    layer: str = ""
    node: str = ""

    class Config:
        """Pydantic 配置 — 允许任意类型。"""
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        """返回 LLM 类型标识。"""
        return "gateway_chat_model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成 — 不支持，请使用 _agenerate。"""
        raise NotImplementedError("GatewayChatModel 仅支持异步接口，请使用 ainvoke")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步生成 — 将 LangChain messages 转为 Gateway prompt 调用。

        Args:
            messages: LangChain 消息列表。
            stop: 停止词列表。
            run_manager: 回调管理器。
            **kwargs: 额外参数（model, temperature 等）。

        Returns:
            ChatResult 包含生成的 AIMessage。
        """
        prompt = self._messages_to_prompt(messages)
        model = kwargs.get("model", self.default_model)

        try:
            resp = await self.gateway.complete(
                prompt=prompt,
                task_type=self.task_type,
                layer=self.layer,
                node=self.node,
                model=model,
            )
            content = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as exc:
            logger.error("Gateway LLM 调用失败: layer=%s, node=%s, error=%s", self.layer, self.node, exc)
            raise

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))],
        )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """异步流式生成 — 通过 Gateway.stream_complete() 实现。

        Args:
            messages: LangChain 消息列表。
            stop: 停止词列表。
            run_manager: 回调管理器。
            **kwargs: 额外参数。

        Yields:
            ChatGenerationChunk 流式 Token。
        """
        prompt = self._messages_to_prompt(messages)
        model = kwargs.get("model", self.default_model)

        try:
            async for token in self.gateway.stream_complete(
                prompt=prompt,
                task_type=self.task_type,
                layer=self.layer,
                node=self.node,
                model=model,
            ):
                chunk_content = token if isinstance(token, str) else token.content
                yield ChatGenerationChunk(message=AIMessageChunk(content=chunk_content))
        except Exception as exc:
            logger.error("Gateway 流式调用失败: layer=%s, node=%s, error=%s", self.layer, self.node, exc)
            raise

    @staticmethod
    def _messages_to_prompt(messages: list[BaseMessage]) -> str:
        """将 LangChain 消息列表转为 Gateway 文本 Prompt。

        Args:
            messages: LangChain 消息列表。

        Returns:
            拼接后的文本 Prompt。
        """
        lines: list[str] = []
        for msg in messages:
            role = msg.type
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if role == "system":
                lines.append(f"System: {content}")
            elif role == "human":
                lines.append(f"User: {content}")
            elif role == "ai":
                lines.append(f"Assistant: {content}")
            else:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """返回模型标识参数（用于 LangSmith 追踪）。"""
        return {
            "model": self.default_model,
            "task_type": self.task_type,
            "layer": self.layer,
            "node": self.node,
        }
