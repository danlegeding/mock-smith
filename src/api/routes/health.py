"""健康检查：给外部一个不花钱的探活入口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from src.db import check_db

router = APIRouter(tags=["运维"])


@router.get("/health", summary="探活：服务 + 数据库")
async def health() -> dict[str, Any]:
    """返回服务与数据库状态。"""
    try:
        db_status = await run_in_threadpool(check_db)
    except Exception as exc:  # noqa: BLE001 - 探活要吞异常，只报告状态
        return {"status": "error", "db": {"error": str(exc)}}
    return {"status": "ok", "db": db_status}
