"""结构化日志模块。"""

from __future__ import annotations

import logging
import sys
from typing import Any


def setup_logger(name: str = "prd2tsd", level: int = logging.INFO) -> logging.Logger:
    """配置并返回结构化日志记录器。

    Args:
        name: 日志记录器名称。
        level: 日志级别，默认 INFO。

    Returns:
        配置好的 Logger 实例。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        "[%(asctime)s] %(name)s %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logger()


def get_logger(name: str | None = None) -> logging.Logger:
    """获取指定名称的日志记录器。

    Args:
        name: 子日志记录器名称，例如 "prd2tsd.auth"。

    Returns:
        Logger 实例。
    """
    if name:
        return logging.getLogger(name)
    return logger


def log_error(logger: logging.Logger, msg: str, **extra: Any) -> None:
    """记录错误日志并附带额外上下文。

    Args:
        logger: 日志记录器。
        msg: 错误消息。
        extra: 额外上下文键值对。
    """
    extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
    if extra_str:
        logger.error("%s | %s", msg, extra_str)
    else:
        logger.error(msg)
