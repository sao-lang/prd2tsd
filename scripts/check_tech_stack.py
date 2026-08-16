"""技术栈合规检查 — 以 tech-stack.yml 为唯一事实源。

替代旧的 grep 式检查：旧 job 用 grep 禁止 langchain/redis/celery，
但这些是 pyproject.toml 明确声明的依赖（门禁与现状矛盾）。
本脚本只校验 tech-stack.yml 中声明的黑名单（forbidden / excluded）。

Usage:
    python scripts/check_tech_stack.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TECH_STACK_FILE = PROJECT_ROOT / "tech-stack.yml"
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
APP_DIR = PROJECT_ROOT / "app"


def load_tech_stack(path: Path = TECH_STACK_FILE) -> dict:
    """加载 tech-stack.yml。

    Args:
        path: tech-stack.yml 路径。

    Returns:
        解析后的配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在时抛出。
    """
    if not path.exists():
        raise FileNotFoundError(f"技术栈配置文件不存在: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def collect_forbidden() -> list[str]:
    """收集 tech-stack.yml 中声明的黑名单包名。

    Returns:
        去重后的黑名单列表（forbidden + excluded）。
    """
    config = load_tech_stack()
    forbidden = list(config.get("forbidden", []) or [])
    excluded = list(config.get("excluded", []) or [])
    return list(dict.fromkeys(forbidden + excluded))


def check_requirements(forbidden: list[str], req_text: str | None = None) -> list[str]:
    """检查 requirements.txt 中是否出现黑名单包。

    Args:
        forbidden: 黑名单包名列表。
        req_text: requirements.txt 内容（测试可注入）。

    Returns:
        违规包名列表（空表示合规）。
    """
    if req_text is None:
        req_text = REQUIREMENTS_FILE.read_text(encoding="utf-8")
    violations: list[str] = []
    for pkg in forbidden:
        # 包名可能以 - 或 _ 形式出现（pip 规范），将 - 替换为字符类后整体转义
        pattern = re.escape(pkg).replace(r"\-", "[-_]")
        if re.search(pattern, req_text, re.IGNORECASE):
            violations.append(pkg)
    return violations


def check_imports(forbidden: list[str], app_dir: Path = APP_DIR) -> list[str]:
    """扫描 app/ 下所有 .py 文件的 import，检查是否引入黑名单模块。

    Args:
        forbidden: 黑名单模块名列表。
        app_dir: 扫描目录。

    Returns:
        违规模块名列表（空表示合规）。
    """
    if not app_dir.exists():
        return []
    import_lines: list[str] = []
    for py_file in app_dir.rglob("*.py"):
        import_lines.extend(py_file.read_text(encoding="utf-8").splitlines())

    violations: list[str] = []
    for mod in forbidden:
        norm = mod.replace("-", "_")
        if any(re.search(rf"(^|\s)(import|from)\s+{re.escape(norm)}\b", line) for line in import_lines):
            violations.append(mod)
    return violations


def main() -> int:
    """执行合规检查并输出结果。

    Returns:
        0 表示合规，1 表示存在违规。
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK 控制台兼容
    forbidden = collect_forbidden()
    req_violations = check_requirements(forbidden)
    import_violations = check_imports(forbidden)

    if req_violations or import_violations:
        for pkg in req_violations:
            print(f"❌ requirements.txt 包含禁止依赖: {pkg}")
        for mod in import_violations:
            print(f"❌ app/ 引入禁止模块: {mod}")
        return 1
    print("✅ 技术栈合规检查通过（黑名单来自 tech-stack.yml）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
