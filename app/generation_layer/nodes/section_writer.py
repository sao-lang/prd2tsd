"""SectionWriterNode — 单节 Worker（由 Send() 扇出调用）。

Block E 增强：SSE 流式推送 — 逐 chunk 推送文档片段。
"""

from __future__ import annotations

from typing import Any

from app.generation_layer.models import GenerationState
from app.llm_gateway import gateway

SECTION_PROMPT = """你是一个技术文档作者。撰写以下技术方案文档章节。

项目：{project}
架构模式：{pattern}
章节：{title}

技术栈：
{stack}

组件：
{components}

请生成该章节的完整 Markdown 内容。
"""


def _format_stack(state: GenerationState) -> str:
    """格式化技术栈文本。"""
    pr = state.get("planning_result")
    if not pr or not pr.tech_stack:
        return "详见技术栈章节"
    return "\n".join(
        f"- {t.dimension}: {t.recommendation}（{t.reason}）" for t in pr.tech_stack
    )


def _format_components(state: GenerationState) -> str:
    """格式化组件文本。"""
    pr = state.get("planning_result")
    if not pr or not pr.components:
        return "详见组件分解章节"
    return "\n".join(
        f"- {c.name}（{c.type}）: {c.responsibility}" for c in pr.components
    )


class SectionWriterNode:
    """章节撰写节点：由 Send() 扇出，每个实例只写一篇章节。

    Block E 增强：
    - 使用 gateway.stream_complete() 流式调用 LLM
    - 通过 EventBus 推送 generation.section / generation.chunk 事件
    """

    async def run(self, state: GenerationState) -> dict[str, Any]:
        """执行单节撰写。

        Args:
            state: 当前状态，需含 _section_target（由 Send 注入）。

        Returns:
            更新后的状态，含该节的 section_contents。
        """
        section = state.get("_section_target")
        if section is None:
            return {"section_contents": {}}

        ar = state.get("analysis_result")
        project_name = ar.project_name if ar else ""
        pattern = ""
        pr = state.get("planning_result")
        if pr:
            pattern = pr.architecture_pattern

        prompt = SECTION_PROMPT.format(
            project=project_name,
            pattern=pattern,
            title=section.title,
            stack=_format_stack(state),
            components=_format_components(state),
        )

        # Block E: 流式调用 + SSE 事件推送
        task_id = state.get("task_id", "")
        section_name = section.title
        section_id = section.section_id

        # 推送 section 开始事件
        await _emit_generation_event(
            task_id, "generation.section",
            {"section_id": section_id, "section_name": section_name, "status": "generating"},
        )

        full_content_parts: list[str] = []
        chunk_buffer = ""
        chunk_threshold = 200  # 每 200 字符推送一个 chunk

        async for token in gateway.stream_complete(
            prompt=prompt,
            task_type="generation.section_writer",
            layer="generation",
            node="section_writer",
        ):
            full_content_parts.append(token)
            chunk_buffer += token

            # 达到阈值时推送 chunk 事件
            if len(chunk_buffer) >= chunk_threshold:
                await _emit_generation_event(
                    task_id, "generation.chunk",
                    {"section_id": section_id, "section_name": section_name, "content": chunk_buffer},
                )
                chunk_buffer = ""

        # 推送剩余内容
        if chunk_buffer:
            await _emit_generation_event(
                task_id, "generation.chunk",
                {"section_id": section_id, "section_name": section_name, "content": chunk_buffer},
            )

        # 推送 section 完成事件
        await _emit_generation_event(
            task_id, "generation.section",
            {"section_id": section_id, "section_name": section_name, "status": "done"},
        )

        content = "".join(full_content_parts)

        # 只返回自己写的这一节，reducer merge_contents 自动合并
        return {
            "section_contents": {section.section_id: content},
        }


async def _emit_generation_event(task_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """向 EventBus 推送生成层事件。

    无 task_id 时静默跳过（非流式场景兼容）。

    Args:
        task_id: 任务 ID。
        event_type: 事件类型。
        payload: 事件数据。
    """
    if not task_id:
        return
    from app.streaming.event_bus import event_bus
    from app.streaming.models import SseEvent

    event = SseEvent(type=event_type, payload=payload)
    await event_bus.publish(f"task:{task_id}", event)
