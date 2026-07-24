"""注释完整性 + ruff 零错误。"""

from __future__ import annotations

import ast
import os


def _get_py_files(directory: str) -> list[str]:
    """递归获取目录下所有 Python 文件。

    Args:
        directory: 目录路径。

    Returns:
        Python 文件路径列表。
    """
    py_files: list[str] = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files


def test_all_functions_have_docstrings():
    """扫描 app/ 下所有 .py 文件，检查每个 public 函数是否有 docstring。"""
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    if not os.path.exists(app_dir):
        pytest.skip("app 目录不存在")

    files_without_docstring: list[str] = []
    for py_file in _get_py_files(app_dir):
        with open(py_file, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                files_without_docstring.append(f"{py_file}: SyntaxError")
                continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 只检查 public 函数（不以 _ 开头）
                if node.name.startswith("_"):
                    continue
                # 检查是否有 docstring
                if not (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)):
                    files_without_docstring.append(f"{py_file}:{node.lineno} {node.name}")

    if files_without_docstring:
        msg = "\n".join(files_without_docstring[:20])
        pytest.fail(f"以下函数缺少 docstring（前 20 个）:\n{msg}")


def test_no_todo_or_fixme():
    """扫描 app/ 下所有 .py 文件，检查无 TODO/FIXME（VIBE_DEFER 除外）。"""
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    if not os.path.exists(app_dir):
        pytest.skip("app 目录不存在")

    violations: list[str] = []
    for py_file in _get_py_files(app_dir):
        with open(py_file, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if ("TODO" in stripped or "FIXME" in stripped) and "VIBE_DEFER" not in stripped:
                    violations.append(f"{py_file}:{i} {stripped.strip()}")

    if violations:
        msg = "\n".join(violations[:20])
        pytest.fail(f"发现 TODO/FIXME（前 20 个）:\n{msg}")


import pytest  # noqa: E402
