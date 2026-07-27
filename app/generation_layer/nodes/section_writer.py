"""SectionWriterNode — 单节 Worker（由 Send() 扇出调用）。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState
from app.generation_layer.tools import call_llm_async

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
    """章节撰写节点：由 Send() 扇出，每个实例只写一篇章节。"""

    async def run(self, state: GenerationState) -> GenerationState:
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
        content = await call_llm_async(prompt, model="deepseek-v3")

        # 只返回自己写的这一节，reducer merge_contents 自动合并
        return {
            "section_contents": {section.section_id: content},
        }
