"""健康检查：给外部一个不花钱的探活入口。

谁在用：Docker healthcheck、前端启动时探一下、面试演示时说"你看服务是活的"。
故意不返回模型/密钥信息——`/health` 通常不需要鉴权，别把内部细节漏出去。

返回形状（契约，别改字段名：scripts/check_api.py 依赖它）：
    {"status": "ok", "db": {"ok": true, "vector": true, "checkpoint_tables": true}}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from src.db import check_db

router = APIRouter(tags=["运维"])


@router.get("/health", summary="探活：服务 + 数据库")
async def health() -> dict[str, Any]:
    """返回服务与数据库状态。

    数据库挂了不抛 500，而是 `status=error`——探活接口自己挂了，
    运维就看不出「是服务挂了还是数据库挂了」。
    """
    try:
        db_status = await run_in_threadpool(check_db)
    except Exception as exc:  # noqa: BLE001 - 探活要吞异常，只报告状态
        return {"status": "error", "db": {"error": str(exc)}}
    return {"status": "ok", "db": db_status}
