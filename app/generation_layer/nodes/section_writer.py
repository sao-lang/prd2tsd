"""SectionWriterNode — 逐节撰写文档内容。"""

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


class SectionWriterNode:
    """章节撰写节点：逐节撰写（批量 1-2 节）。"""

    async def run(self, state: GenerationState) -> GenerationState:
        """执行章节撰写。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 section_contents。
        """
        pr = state["planning_result"]
        ar = state["analysis_result"]
        outline = state.get("outline", [])
        contents = dict(state.get("section_contents", {}))

        stack_text = "\n".join(
            f"- {t.dimension}: {t.recommendation}（{t.reason}）" for t in pr.tech_stack
        )
        comp_text = "\n".join(
            f"- {c.name}（{c.type}）: {c.responsibility}" for c in pr.components
        )

        for section in outline[:3]:  # 每轮最多写 3 节
            if section.section_id in contents:
                continue

            prompt = SECTION_PROMPT.format(
                project=ar.project_name,
                pattern=pr.architecture_pattern,
                title=section.title,
                stack=stack_text or "详见技术栈章节",
                components=comp_text or "详见组件分解章节",
            )
            content = await call_llm_async(prompt, model="deepseek-v3")
            contents[section.section_id] = content

        return {
            **state,
            "section_contents": contents,
        }
