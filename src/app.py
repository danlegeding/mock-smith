"""FastAPI 接口层：把 LangGraph 图包成 HTTP 服务。

## 这一层为什么这么薄

所有业务判断都在图里（出题、评分、决策、报告），接口层只做四件事：

1. 把 HTTP 请求翻译成「图的一次 invoke」或「Command(resume=...)」
2. 把图停在 interrupt 上的问题翻译成 `TurnOut`
3. 会话 / 报告的落库（Tortoise）
4. 把异常翻译成 HTTP 状态码

**别在这里加业务规则**——加在这里的规则不会被 checkpointer 记录，也进不了 gold 集评测。

## 一个必须知道的实现细节：sync 图 + async 框架

图是同步的（psycopg 连接池是同步的），FastAPI 是异步的。
直接把 `graph.invoke()` 写在 async 端点里会**卡住整个事件循环**，所有并发请求一起变慢。
所以每次调用都套一层 `run_in_threadpool`，让它去线程里跑。

## 启动

    conda activate interview-agent
    uvicorn src.app:app --reload --port 8000

文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from langgraph.types import Command

from src.db import close_pool
from src.graph.build import build_persistent_graph
from src.model import (
    DIMENSIONS,
    AnswerIn,
    Question,
    Report,
    SessionCreate,
    TurnOut,
)
from src.orm import close_db, init_db
from src.orm_models import ReportRecord, SessionRecord

_graph: Any = None


def get_graph() -> Any:
    """进程内只编译一次图（每次重编译会新建连接池）。"""
    global _graph
    if _graph is None:
        _graph = build_persistent_graph()
    return _graph


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动时建表 + 建连接池，关闭时都释放掉。"""
    await init_db(global_fallback=True)
    get_graph()
    yield
    await close_db()
    close_pool()


app = FastAPI(title="模拟面试 Agent", version="0.1.0", lifespan=lifespan)


def _config(session_id: str) -> dict[str, Any]:
    """LangGraph 的会话配置：thread_id 就是 session_id，两者必须一致。"""
    return {"configurable": {"thread_id": session_id}}


def _pending_question(graph: Any, config: dict[str, Any]) -> dict[str, Any] | None:
    """图停在哪个 interrupt 上，就把那个问题取出来；停不下来说明跑完了。"""
    snapshot = graph.get_state(config)
    for task in snapshot.tasks:
        for item in task.interrupts:
            return item.value
    return None


def _build_turn_out(session_id: str, graph: Any, config: dict[str, Any]) -> TurnOut:
    """把"图当前停在哪"翻译成接口的返回：下一题，或者最终报告。"""
    values = graph.get_state(config).values
    turns = values.get("turns") or []
    payload = _pending_question(graph, config)

    if payload is not None:
        return TurnOut(
            session_id=session_id,
            type="question",
            question=Question.model_validate(payload),
            turn_index=len(turns),
        )

    report = values.get("report")
    if report is None:
        # 跑完了却没有报告：说明图配置错了或哪个节点吞了异常，值得 500
        raise HTTPException(status_code=500, detail="面试已结束但没有生成报告")
    return TurnOut(
        session_id=session_id,
        type="report",
        report=Report.model_validate(report),
        turn_index=len(turns),
    )


async def _save_report_if_finished(session_id: str, values: dict[str, Any]) -> None:
    """报告生成后落库一次，并把会话标成 finished（重复调用不会写两份）。"""
    report = values.get("report")
    if not report:
        return

    session = await SessionRecord.get_or_none(session_id=session_id)
    if session is None or session.status == "finished":
        return

    turns = values.get("turns") or []
    averages: dict[str, float] = report.get("dimension_summary") or {}
    overall_score = round(sum(averages.values()) / len(averages), 2) if averages else 0.0
    asked = {turn["question"]["dimension"] for turn in turns}
    skipped_dims = [d.value for d in DIMENSIONS if d.value not in asked]

    await ReportRecord.create(
        session=session,
        overall=report["overall"],
        overall_score=overall_score,
        dimension_summary=averages,
        strengths=report.get("strengths", []),
        weaknesses=report.get("weaknesses", []),
        gap_conclusion=report.get("gap_conclusion", ""),
        next_steps=report.get("next_steps", []),
        turns_used=len(turns),
        skipped_dims=skipped_dims,
    )
    session.status = "finished"
    await session.save(update_fields=["status"])


@app.get("/health")
async def health() -> dict[str, str]:
    """探活用：只证明进程起来了。"""
    return {"status": "ok"}


@app.post("/sessions", response_model=TurnOut)
async def create_session(body: SessionCreate) -> TurnOut:
    """开始一场面试：解析 JD + 简历、判档、出题，直接返回第一题。"""
    session_id = uuid.uuid4().hex[:16]
    graph = get_graph()
    config = _config(session_id)

    try:
        await run_in_threadpool(
            graph.invoke,
            {"jd_text": body.jd_text, "resume_text": body.resume_text},
            config,
        )
    except Exception as exc:  # noqa: BLE001 - 启动失败要把原因带给调用方
        raise HTTPException(status_code=500, detail=f"启动面试失败：{exc}") from exc

    values = graph.get_state(config).values
    jd_title = (values.get("jd_profile") or {}).get("role_title", "")
    await SessionRecord.create(session_id=session_id, jd_title=jd_title[:200])
    return _build_turn_out(session_id, graph, config)


@app.post("/sessions/{session_id}/answer", response_model=TurnOut)
async def answer(session_id: str, body: AnswerIn) -> TurnOut:
    """回答当前这一题（或者跳过）：图会自动评分、决策、并给出下一题。"""
    session = await SessionRecord.get_or_none(session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status == "finished":
        raise HTTPException(status_code=409, detail="面试已经结束，可以 GET /report 看报告")

    graph = get_graph()
    config = _config(session_id)
    if _pending_question(graph, config) is None:
        raise HTTPException(status_code=409, detail="当前没有待回答的题目")

    # 空回答按跳过处理：接口上"跳过"和"答了但没内容"是同一件事
    reply = {"text": body.answer} if body.answer.strip() else {"skip": True}
    try:
        await run_in_threadpool(graph.invoke, Command(resume=reply), config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"回答处理失败：{exc}") from exc

    values = graph.get_state(config).values
    await _save_report_if_finished(session_id, values)
    return _build_turn_out(session_id, graph, config)


@app.get("/sessions/{session_id}/report", response_model=Report)
async def get_report(session_id: str) -> Report:
    """取最终报告（面完才有的看）。"""
    record = await ReportRecord.get_or_none(session__session_id=session_id)
    if record is None:
        session = await SessionRecord.get_or_none(session_id=session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        raise HTTPException(status_code=409, detail="面试还没结束，没有报告")

    return Report(
        overall=record.overall,
        dimension_summary=record.dimension_summary,
        strengths=record.strengths,
        weaknesses=record.weaknesses,
        gap_conclusion=record.gap_conclusion,
        next_steps=record.next_steps,
    )


@app.get("/sessions")
async def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """最近几场面试（给前端/Streamlit 列表用）。"""
    records = await SessionRecord.all().order_by("-created_at").limit(min(limit, 100))
    return [
        {
            "session_id": record.session_id,
            "jd_title": record.jd_title,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
        for record in records
    ]
