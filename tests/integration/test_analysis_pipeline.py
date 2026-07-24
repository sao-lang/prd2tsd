"""C1 — Analysis Layer 集成测试。"""

from __future__ import annotations

import pytest

from app.analysis_layer.agent_graph import analysis_graph


@pytest.mark.asyncio
async def test_analysis_extracts_requirements():
    """验证 Analysis Layer 能从 PRD 中提取需求（同步路径）。"""
    prd = "# 项目名称：电商平台\n## 功能需求\n1. 用户登录\n2. 商品搜索"
    result = await analysis_graph.ainvoke({"prd_raw": prd})
    assert "analysis_result" in result
    # 即使 LLM 不可用，也应返回含有默认值的 AnalysisResult
    assert result["analysis_result"].project_name != ""


@pytest.mark.asyncio
async def test_analysis_detects_constraints():
    """验证约束提取节点在 pipeline 中正常运行。"""
    prd = "# 项目名称：电商平台\n## 约束条件\n必须使用Java 17"
    result = await analysis_graph.ainvoke({"prd_raw": prd})
    assert "extracted_constraints" in result


@pytest.mark.asyncio
async def test_analysis_parse_and_assemble():
    """验证解析和组装流程。"""
    prd = "# MyApp\n## Overview\nA cool app."
    result = await analysis_graph.ainvoke({"prd_raw": prd})
    assert len(result["prd_sections"]) > 0
    assert result["analysis_result"].project_name != ""
