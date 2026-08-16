"""技术栈合规检测。"""

from __future__ import annotations


def test_required_packages_installed():
    """检测必须的包是否在 requirements.txt。"""
    import os

    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    with open(req_path) as f:
        content = f.read().lower()

    required = [
        "fastapi", "sqlalchemy", "alembic", "pydantic-settings",
        "openai", "asyncpg", "langchain-core", "langgraph", "psycopg[binary]",
        "pytest", "ruff", "mypy",
    ]
    for pkg in required:
        assert pkg in content, f"缺少必须的依赖: {pkg}"


def test_forbidden_packages_not_installed():
    """检测禁止的包不在 requirements.txt。"""
    import os

    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    with open(req_path) as f:
        content = f.read().lower()

    forbidden = ["chromadb", "qdrant-client", "flask", "django", "milvus", "pinecone-client"]
    for pkg in forbidden:
        assert pkg not in content, f"发现禁止的依赖: {pkg}"


def test_tech_stack_script_blacklist_matches_config():
    """校验合规脚本的黑名单与 tech-stack.yml 一致。"""
    from scripts.check_tech_stack import collect_forbidden, load_tech_stack

    config = load_tech_stack()
    expected = list(dict.fromkeys((config.get("forbidden", []) or []) + (config.get("excluded", []) or [])))
    assert collect_forbidden() == expected
    assert "chromadb" in collect_forbidden()
    assert "flask" in collect_forbidden()


def test_tech_stack_script_detects_requirements_violations():
    """验证合规脚本能识别 requirements.txt 中的黑名单包。"""
    from scripts.check_tech_stack import check_requirements

    assert check_requirements(["chromadb"], "fastapi>=0.110\nchromadb==0.5.0\n") == ["chromadb"]
    # 连字符/下划线归一化匹配
    assert check_requirements(["qdrant-client"], "qdrant_client>=1.0\n") == ["qdrant-client"]
    # 合规内容不误报
    assert check_requirements(["flask", "django"], "fastapi\nuvicorn\nlangchain-core\nredis\ncelery\n") == []


def test_tech_stack_script_detects_import_violations(tmp_path):
    """验证合规脚本能识别 app/ 中的黑名单 import。"""
    from scripts.check_tech_stack import check_imports

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "bad_module.py").write_text(
        "import chromadb\nfrom milvus import Collection\n",
        encoding="utf-8",
    )
    (app_dir / "good_module.py").write_text(
        "from fastapi import FastAPI\nimport redis\n",
        encoding="utf-8",
    )

    violations = check_imports(["chromadb", "milvus", "flask"], app_dir=app_dir)
    assert "chromadb" in violations
    assert "milvus" in violations
    assert "flask" not in violations
