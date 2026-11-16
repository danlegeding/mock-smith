"""统一日志：一处配置，所有模块共用。"""

from __future__ import annotations

import logging
import os

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_configured = False


def _configure_once() -> None:
    """全局配置只做一次；已经有人配过（比如 uvicorn）就只调级别。"""
    global _configured
    if _configured:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format=os.getenv("LOG_FORMAT", _DEFAULT_FORMAT),
            datefmt="%H:%M:%S",
        )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """取一个模块级 logger（首次调用时顺带完成全局配置）。"""
    _configure_once()
    return logging.getLogger(name)
