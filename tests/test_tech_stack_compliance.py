"""技术栈合规检测。"""

from __future__ import annotations


def test_no_langchain_import():
    """检测是否有 langchain 被引入。"""
    import sys

    for mod_name in list(sys.modules.keys()):
        if "langchain" in mod_name.lower():
            pytest.fail(f"禁止引入 langchain: {mod_name}")


def test_required_packages_installed():
    """检测必须的包是否在 requirements.txt。"""
    import os

    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    with open(req_path) as f:
        content = f.read().lower()

    required = ["fastapi", "sqlalchemy", "alembic", "pydantic-settings",
                "openai", "asyncpg", "pytest", "ruff", "mypy"]
    for pkg in required:
        assert pkg in content, f"缺少必须的依赖: {pkg}"


def test_forbidden_packages_not_installed():
    """检测禁止的包不在 requirements.txt。"""
    import os

    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    with open(req_path) as f:
        content = f.read().lower()

    forbidden = ["langchain", "chromadb", "qdrant-client", "flask", "django"]
    for pkg in forbidden:
        assert pkg not in content, f"发现禁止的依赖: {pkg}"


import pytest  # noqa: E402 (must be after function defs for module-level import)
