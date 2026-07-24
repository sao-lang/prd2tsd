"""TemplateEngine — ⭐ 模板引擎单元测试。"""

from __future__ import annotations

from app.generation_layer.templates.engine import TemplateEngine


def test_template_engine_select_default():
    """验证模板引擎能选择默认行业模板。"""
    engine = TemplateEngine()
    tmpl = engine.select_template("unknown_industry")
    assert tmpl is None or tmpl.endswith("default.yaml")


def test_template_engine_render_section():
    """验证模板引擎能渲染章节模板。"""
    engine = TemplateEngine()
    result = engine.render_section("background", project_name="Test", domain="tech", summary="", requirements=[], constraints=[])
    assert "项目背景" in result


def test_template_engine_render_architecture():
    """验证模板引擎能渲染架构章节。"""
    engine = TemplateEngine()
    result = engine.render_section("architecture", architecture_pattern="微服务", component_diagram="graph TD", components=[])
    assert "总体架构" in result
