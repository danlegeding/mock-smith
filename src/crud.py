"""业务表的全部读写都在这里（sessions / reports）。"""

from __future__ import annotations

from typing import Any

from src.orm_models import ReportRecord, SessionRecord


# ------------------------------------------------------------------ 会话 sessions
async def create_session(session_id: str, jd_title: str) -> SessionRecord:
    """建一行会话。`session_id` 同时是 LangGraph 的 `thread_id`。"""
    return await SessionRecord.create(session_id=session_id, jd_title=jd_title[:200])


async def get_session(session_id: str) -> SessionRecord | None:
    """按主键查一行；查不到返回 None（不抛异常，让调用方决定 404 还是别的）。"""
    return await SessionRecord.get_or_none(session_id=session_id)


async def list_sessions(limit: int = 20) -> list[SessionRecord]:
    """最近的会话，按创建时间倒序。`limit` 上限 100，防止前端一次要一万条。"""
    return await SessionRecord.all().order_by("-created_at").limit(min(limit, 100))


async def finish_session(session: SessionRecord) -> None:
    """把会话标成已结束。只更新 status 一列，不碰别的字段。"""
    session.status = "finished"
    await session.save(update_fields=["status"])


# ------------------------------------------------------------------ 报告 reports
async def save_report(session: SessionRecord, report: dict[str, Any], **extra: Any) -> ReportRecord:
    """把图里生成的报告落成一行，外键指回会话。"""
    return await ReportRecord.create(session=session, **report, **extra)


async def get_report(session_id: str) -> ReportRecord | None:
    """按会话 id 查报告；查不到返回 None。"""
    return await ReportRecord.get_or_none(session_id=session_id)
