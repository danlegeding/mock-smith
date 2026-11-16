"""GET /sessions —— 会话列表。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src import crud

router = APIRouter(tags=["面试"])


@router.get("/sessions", response_model=list[dict], summary="会话列表")
async def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """最近创建的会话，按创建时间倒序。返回数组，不是 `{"sessions": [...]}`。"""
    rows = await crud.list_sessions(limit)
    return [
        {
            "session_id": row.session_id,
            "jd_title": row.jd_title,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
