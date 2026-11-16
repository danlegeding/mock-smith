"""练手脚本：用「脚本方式」练 Tortoise 的增删改查（仿 fastapi_code/16 的写法）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tortoise import Tortoise, run_async  # noqa: E402

from src.orm import tortoise_config  # noqa: E402
from src.orm_models import ReportRecord, SessionRecord  # noqa: E402

DEMO_ID = "demo-crud-001"


# 固定写法：连库 + 建表
# 教程里是 Tortoise.init(db_url='mysql://...', modules={'models': ['model16']})，
# 这是「单库简写」；我们项目用完整版 tortoise_config()，因为要指定 asyncpg 引擎和连接池参数。
async def init() -> None:
    await Tortoise.init(config=tortoise_config())
    await Tortoise.generate_schemas(safe=True)  # safe=True → CREATE TABLE IF NOT EXISTS
    print("[init] 连库 + 建表完成")


# 增
async def create_session(session_id: str, jd_title: str) -> SessionRecord:
    session = await SessionRecord.create(session_id=session_id, jd_title=jd_title)
    print(f"[增] {session}")
    return session


# 查单条（主键）
async def get_session(session_id: str) -> SessionRecord | None:
    session = await SessionRecord.get_or_none(session_id=session_id)
    print(f"[查单条] {session}")
    return session


# 查多条（条件过滤）
async def list_active() -> list[SessionRecord]:
    sessions = await SessionRecord.filter(status="active")
    print(f"[查多条] 进行中的会话 {len(sessions)} 条")
    return sessions


# 模糊查（字段名 __ 操作符）
async def search_by_title(keyword: str) -> list[SessionRecord]:
    sessions = await SessionRecord.filter(jd_title__contains=keyword)
    print(f"[模糊查] 标题含「{keyword}」的会话 {len(sessions)} 条")
    return sessions


# 改：先 get 出对象，改属性，再 save()（不是 update 语句直发）
async def finish_session(session_id: str) -> SessionRecord:
    session = await SessionRecord.get(session_id=session_id)
    session.status = "finished"
    await session.save()
    print(f"[改] 状态改成 {session.status}")
    return session


# 删
async def delete_session(session_id: str) -> None:
    session = await SessionRecord.get_or_none(session_id=session_id)
    if session is None:
        print("[删] 记录不存在，跳过")
        return
    await session.delete()
    print("[删] 已删除（关联的报告会跟着级联删除）")


# 外键：一条会话挂一条报告
async def create_report(session_id: str) -> ReportRecord:
    report = await ReportRecord.create(
        session_id=session_id,  # 外键可以直接传主键值
        overall="演示报告：候选人基础扎实但缺少量化数据",
        overall_score=3.2,
        dimension_summary={"tech_depth": 3.5, "communication": 3.0},
        strengths=[{"point": "能把流程讲清楚", "evidence_quote": "先定契约再补测试"}],
        weaknesses=[{"point": "缺少数字", "evidence_quote": "大概快了一些", "suggestion": "补量化对比"}],
        gap_conclusion="对照 JD，缺少部署与评测经验",
        next_steps=["跑一次 hit@k", "补 Docker 部署", "准备一个 STORY"],
        turns_used=6,
        skipped_dims=["job_match"],
    )
    print(f"[外键] 报告已写入，id={report.id}")
    return report


# 外键：从报告取回会话（验证 relationship 真的能用）
async def report_with_session() -> None:
    report = await ReportRecord.filter(session_id__startswith="demo-").first().prefetch_related("session")
    if report is None:
        print("[外键] 还没报告，跳过")
        return
    print(f"[外键] 报告 {report.id} 属于会话 {report.session.session_id}（{report.session.jd_title}）")


# 手写数据（对应教程里的 main()）
async def main() -> None:
    await init()

    await create_session(DEMO_ID, "AI Agent 开发实习生")
    await get_session(DEMO_ID)
    await list_active()
    await search_by_title("Agent")

    await create_report(DEMO_ID)
    await report_with_session()

    await finish_session(DEMO_ID)
    await list_active()

    # 清理：删会话 → 报告级联删除
    await delete_session(DEMO_ID)
    await ReportRecord.filter(session_id__startswith="demo-").delete()
    await Tortoise.close_connections()
    print("[done] 演示结束，演示数据已清理")


if __name__ == "__main__":
    run_async(main())
