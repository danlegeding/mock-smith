"""统一日志：一处配置，所有模块共用。

为什么服务端不用 `print`：

- **不能分级**：想要「只看错误」做不到；
- **不能关**：`GRAPH_TRACE=0` 只能关掉工具打印，节点里的 print 还在；
- **没有上下文**：没时间戳、没模块名，多进程/高并发时日志交错，分不清是哪一场面试；
- **stdout 阻塞**：高并发下是隐性瓶颈。

`scripts/` 里的 `print` 是刻意保留的——那是命令行工具的界面，不是服务端日志。

用法：

    from src.log import get_logger

    logger = get_logger(__name__)
    logger.info("题池 %s 道", len(kept))

级别由环境变量 `LOG_LEVEL` 控制（默认 `INFO`，可设 `DEBUG` / `WARNING`），
格式可用 `LOG_FORMAT` 覆盖。第一次调用 `get_logger` 时完成全局配置，
所以不管是 uvicorn 起的、脚本起的，输出格式都一致。
"""

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
    """取一个模块级 logger（首次调用时顺带完成全局配置）。

    模块顶部写 `logger = get_logger(__name__)`，日志里就会自动带模块名。
    """
    _configure_once()
    return logging.getLogger(name)
