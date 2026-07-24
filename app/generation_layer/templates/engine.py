"""TemplateEngine — ⭐ Jinja2 模板引擎。"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class TemplateEngine:
    """三级模板引擎（行业/企业/章节）。

    按优先级：行业模板 > 章节模板 > 默认模板。
    """

    def __init__(self, template_dir: str | None = None) -> None:
        """初始化模板引擎。

        Args:
            template_dir: 模板根目录。默认为本文件所在目录。
        """
        if template_dir is None:
            template_dir = str(Path(__file__).parent)
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
        )

    def select_template(self, industry: str = "default") -> str | None:
        """按行业选择模板。

        Args:
            industry: 行业名称。

        Returns:
            模板路径，未找到时返回 None。
        """
        candidates = [
            f"industry/{industry}.yaml",
            "industry/default.yaml",
        ]
        for name in candidates:
            try:
                self.env.get_template(name)
                return name
            except Exception:
                continue
        return None

    def render_section(self, section_name: str, **kwargs: Any) -> str:
        """渲染章节模板。

        Args:
            section_name: 模板名（如 "background"）。
            **kwargs: 模板变量。

        Returns:
            渲染后的内容。
        """
        try:
            template = self.env.get_template(f"section/{section_name}.md")
            return template.render(**kwargs)
        except Exception:
            return ""

    def render(self, template_name: str, **kwargs: Any) -> str:
        """渲染任意模板。

        Args:
            template_name: 模板路径。
            **kwargs: 模板变量。

        Returns:
            渲染后的内容。
        """
        try:
            template = self.env.get_template(template_name)
            return template.render(**kwargs)
        except Exception:
            return ""


from typing import Any
