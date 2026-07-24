"""OutlineGeneratorNode — 生成文档大纲。"""

from __future__ import annotations

from app.generation_layer.models import GenerationState
from contracts.interfaces import SectionOutline


class OutlineGeneratorNode:
    """大纲生成节点：基于模板和规划结果生成 14 节大纲。"""

    def run(self, state: GenerationState) -> GenerationState:
        """生成文档大纲。

        Args:
            state: 当前状态。

        Returns:
            更新后的状态，含 outline。
        """
        from app.generation_layer.templates.engine import TemplateEngine

        engine = TemplateEngine()
        industry = "ecommerce" if "电商" in str(state["analysis_result"].domain_tags) else "default"
        tmpl_name = engine.select_template(industry)

        # 从模板加载章节
        outline: list[SectionOutline] = []
        if tmpl_name:
            from pathlib import Path

            import yaml
            tmpl_path = Path(__file__).parent.parent / "templates" / tmpl_name
            if tmpl_path.exists():
                with open(tmpl_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                for _i, sec in enumerate(data.get("sections", [])):
                    outline.append(SectionOutline(
                        section_id=sec["id"],
                        title=sec["title"],
                        level=sec.get("level", 1),
                        description="",
                        estimated_tokens=500,
                    ))

        if not outline:
            outline = [
                SectionOutline(
                    section_id="background", title="项目背景", level=1,
                    description="", estimated_tokens=300,
                ),
                SectionOutline(
                    section_id="architecture", title="总体架构", level=1,
                    description="", estimated_tokens=500,
                ),
                SectionOutline(
                    section_id="module_design", title="模块详细设计", level=1,
                    description="", estimated_tokens=800,
                ),
            ]

        return {
            **state,
            "outline": outline,
        }
