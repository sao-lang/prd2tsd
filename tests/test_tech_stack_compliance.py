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
