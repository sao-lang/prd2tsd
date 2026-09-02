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

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
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

    gateway: Any = None
    default_model: str = ""
    task_type: str = "default"
    layer: str = ""
    node: str = ""

    class Config:
        """Pydantic 配置 — 允许任意类型。"""

        arbitrary_types_allowed = True

    def __init__(self, **data: Any) -> None:
        """初始化 GatewayChatModel，未提供 gateway 时自动从全局获取。"""
        super().__init__(**data)
        if self.gateway is None:
            from app.llm_gateway import gateway as _gw

            self.gateway = _gw

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
        """同步生成 — 委托给 _agenerate。

        使用 asyncio 在当前事件循环中运行异步方法。
        如果当前无事件循环，创建新的事件循环执行。

        Args:
            messages: LangChain 消息列表。
            stop: 停止词列表。
            run_manager: 回调管理器。
            **kwargs: 额外参数。

        Returns:
            ChatResult 包含生成的 AIMessage。
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop, **kwargs))

        # 如果已经在事件循环中运行（通常是被 LangChain 回调管理器调用），
        # 通过新线程执行以避免嵌套事件循环冲突
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                self._agenerate(messages, stop, **kwargs),
            )
            return future.result()

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
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
        call_kwargs = dict(kwargs)
        model = call_kwargs.pop("model", self.default_model)
        if model:
            call_kwargs["model"] = model
        if stop:
            call_kwargs["stop"] = stop

        try:
            resp = await self.gateway.complete(
                prompt=prompt,
                task_type=self.task_type,
                layer=self.layer,
                node=self.node,
                **call_kwargs,
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
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
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
        call_kwargs = dict(kwargs)
        model = call_kwargs.pop("model", self.default_model)
        if model:
            call_kwargs["model"] = model
        if stop:
            call_kwargs["stop"] = stop

        try:
            async for token in self.gateway.stream_complete(
                prompt=prompt,
                task_type=self.task_type,
                layer=self.layer,
                node=self.node,
                **call_kwargs,
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
