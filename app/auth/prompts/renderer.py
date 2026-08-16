"""Prompt 渲染器 — 使用 Jinja2 模板引擎注入变量。"""

from __future__ import annotations

from jinja2 import Template


class PromptRenderer:
    """Prompt 渲染器 — 使用 Jinja2 模板引擎注入变量。"""

    def render(self, template_str: str, variables: dict[str, str]) -> str:
        """渲染 Prompt 模板。

        Args:
            template_str: Jinja2 模板字符串。
            variables: 变量字典。

        Returns:
            渲染后的 Prompt。

        模板示例：
        ```
        你是一个 {{ role }}，为 {{ company_name }}（{{ industry }} 行业）设计技术方案。
        该企业的常用技术栈：{{ tech_stack }}
        内部术语：{{ internal_terms }}
        ```
        """
        template = Template(template_str)
        rendered = template.render(**variables)
        assert isinstance(rendered, str)
        return rendered
