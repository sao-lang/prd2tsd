"""CodeScaffoldGeneratorNode — LangChain 生成可编译代码框架。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.generation_layer.models import GenerationState
from app.llm_gateway.langchain_adapter import GatewayChatModel

CODE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个资深开发工程师。根据以下技术方案，生成可编译的代码框架。"),
    ("system",
     "包含：项目目录结构、核心数据模型、API 路由骨架、依赖注入配置。"
     "用 Markdown 代码块输出，确保代码可编译。"),
    ("human", "项目：{project}\n架构模式：{pattern}\n组件：\n{components}\n\n技术栈：\n{stack}"),
])


class CodeScaffoldGeneratorNode:
    """代码框架生成节点：LangChain 链生成可编译代码。"""

    def __init__(self, llm: GatewayChatModel | None = None) -> None:
        if llm is None:
            llm = GatewayChatModel(task_type="generation", layer="generation", node="code_scaffold")
        self.chain = CODE_PROMPT | llm

    async def run(self, state: GenerationState) -> GenerationState:
        """执行代码脚手架生成节点逻辑。"""
        pr = state["planning_result"]
        ar = state["analysis_result"]

        comp_text = "\n".join(f"- {c.name}: {c.responsibility}" for c in pr.components)
        stack_text = "\n".join(f"- {t.dimension}: {t.recommendation}" for t in pr.tech_stack)

        result = await self.chain.ainvoke({
            "project": ar.project_name,
            "pattern": pr.architecture_pattern,
            "components": comp_text,
            "stack": stack_text,
        })
        code = result.content if isinstance(result.content, str) else str(result)
        return {**state, "code_scaffold": code}
