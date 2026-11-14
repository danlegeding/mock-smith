"""业务表的全部读写都在这里（sessions / reports）。

结构照抄 `fastapi_code/16.通过脚本的方式添加数据库数据/crud16.py`：
「一个实体一组 async 函数」——建、查、改、删各一个函数，路由只调这些函数，
不直接写 `SessionRecord.create(...)`。这样 ORM 用在哪、怎么用，只看这一个文件就够。

和教程的三点不同（都是刻意的）：
1. 教程的函数里 `try/except: print(...)` 吞掉异常——脚本里可以，接口里不行：
   吞掉异常会让接口返回 200 假成功，这里**让异常往上抛**，由 `src/api/errors.py` 统一转 500。
2. 教程的 `init()` 在这里不需要：建表由 `src/orm.py` 的 `init_db()` 在应用 lifespan 里做。
3. 教程把 `db_url` 写死在代码里，本项目从 `.env` 读（`src/orm.py` 的 `tortoise_config()`）。
"""

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
    """把图里生成的报告落成一行，外键指回会话。

    `report` 是 `state["report"]`（`Report.model_dump(mode="json")` 的结果）；
    其余统计字段（均分、轮数、未覆盖维度）由调用方算好通过 `extra` 传进来——
    这里只负责「写」，不做业务判断。
    """
    return await ReportRecord.create(session=session, **report, **extra)


async def get_report(session_id: str) -> ReportRecord | None:
    """按会话 id 查报告；查不到返回 None。"""
    return await ReportRecord.get_or_none(session_id=session_id)
