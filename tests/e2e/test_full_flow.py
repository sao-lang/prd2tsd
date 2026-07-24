"""块 D — 端到端全链路测试（真实 LLM 调用）。

运行方式: pytest tests/e2e/test_full_flow.py -v --slow
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.getenv("RUN_E2E_TESTS"),
        reason="设置 RUN_E2E_TESTS=1 以运行端到端测试",
    ),
]

SAMPLE_PRD = """# 用户服务系统设计

## 技术栈

用户服务使用 Spring Boot 3.2 框架，基于 PostgreSQL 15 数据库存储用户数据。
使用 Redis 7 做会话缓存和令牌黑名单。使用 JWT 做身份认证，Token 有效期 15 分钟。
API 采用 RESTful 设计风格，使用 Swagger/OpenAPI 3.0 做接口文档。

## 架构设计

系统采用微服务架构，分为用户服务、认证服务和通知服务三个核心组件。
用户服务负责用户 CRUD 和权限管理，认证服务负责 OAuth2.0 登录和 Token 颁发，
通知服务负责邮件和短信发送。服务之间通过 RabbitMQ 消息队列异步通信。

## 部署与运维

所有服务通过 Docker 容器化部署，使用 Kubernetes 编排。
使用 Prometheus + Grafana 做监控，ELK Stack 做日志收集。
采用 GitHub Actions 做 CI/CD 流水线，代码质量通过 SonarQube 检测。

## 安全约束

密码必须使用 bcrypt 加密存储，敏感数据在传输层使用 TLS 1.3 加密。
API 访问需要 API Key 鉴权，每个请求必须携带有效的 JWT Token。
系统需要支持 GDPR 合规要求，用户数据可导出和删除。
"""


@pytest.mark.asyncio
async def test_full_flow():
    """端到端全链路测试。

    输入：样本 PRD .md
    输出：完整技术方案文档
    验证：文档长度 > 3000 字，包含 mermaid 图表
    """
    # 1. 构建真实 Orchestrator
    from app.analysis_layer.agent_graph import analysis_graph
    from app.evaluation.agent_graph import evaluation_graph
    from app.generation_layer.agent_graph import generation_graph
    from app.planning_layer.agent_graph import planning_graph
    from app.knowledge_layer.pipeline import RetrievalPipeline
    from app.orchestrator.main_graph import build_and_compile
    from app.orchestrator.state import make_initial_state

    pipeline = RetrievalPipeline()

    orchestrator = build_and_compile(
        analysis_graph=analysis_graph,
        planning_graph=planning_graph,
        generation_graph=generation_graph,
        evaluation_graph=evaluation_graph,
        retrieval_pipeline=pipeline,
    )

    # 2. 准备输入
    state = make_initial_state(
        task_id="e2e-test-1",
        prd_raw=SAMPLE_PRD,
        prd_file_type="md",
        max_iterations=3,
    )

    # 3. 执行全链路
    result = await orchestrator.ainvoke(state)

    # 4. 断言
    assert result["status"] == "complete", f"流程未完成: {result.get('error_message', '')}"
    assert result["progress"] == 1.0

    gen_result = result["generation_result"]
    assert gen_result is not None, "生成结果为空"

    # 获取文档内容
    content = ""
    if isinstance(gen_result, dict):
        content = gen_result.get("content", "")
    else:
        content = getattr(gen_result, "content", "")

    assert len(content) > 3000, f"文档长度不足: {len(content)} 字（要求 > 3000）"

    # 验证包含 mermaid 图表
    assert "```mermaid" in content, "文档未包含 mermaid 图表"

    # 5. 验证评测报告
    eval_report = result["evaluation_report"]
    assert eval_report is not None, "评测报告为空"
    if isinstance(eval_report, dict):
        assert eval_report.get("overall_score", 0) > 0, "评测分数异常"
    else:
        assert eval_report.overall_score > 0, "评测分数异常"
