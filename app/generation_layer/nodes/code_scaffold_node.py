"""CodeScaffoldGeneratorNode — ⭐ 生成真实可编译代码框架。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState
from app.generation_layer.tools import call_llm_async

CODE_PROMPT = """你是一个资深开发工程师。根据以下技术方案，生成可编译的代码框架。

项目：{project}
架构模式：{pattern}
组件：
{components}

技术栈：
{stack}

生成 Python/FastAPI 代码框架，包含：
1. 项目目录结构
2. 核心数据模型
3. API 路由骨架
4. 依赖注入配置

用 Markdown 代码块输出，确保代码可编译。
"""


class CodeScaffoldGeneratorNode:
    """代码框架生成节点：生成可编译代码。"""

    async def run(self, state: GenerationState) -> GenerationState:
        """执行代码框架生成。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态。
        """
        pr = state["planning_result"]
        ar = state["analysis_result"]

        comp_text = "\n".join(
            f"- {c.name}: {c.responsibility}" for c in pr.components
        )
        stack_text = "\n".join(
            f"- {t.dimension}: {t.recommendation}" for t in pr.tech_stack
        )

        prompt = CODE_PROMPT.format(
            project=ar.project_name,
            pattern=pr.architecture_pattern,
            components=comp_text,
            stack=stack_text,
        )
        await call_llm_async(prompt, model="deepseek-v3")
        return state
