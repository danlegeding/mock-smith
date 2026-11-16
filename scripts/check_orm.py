"""D1.5 验收：Tortoise ORM 这一层能不能用（读 → 写 → 查 → 外键 → 删）。"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tortoise import Tortoise  # noqa: E402

from src.orm import close_db, init_db  # noqa: E402
from src.orm_models import ReportRecord, SessionRecord  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    """记一条检查结果。不抛异常，最后统一汇总（这样能看到所有问题，而不是第一个就停）。"""
    if ok:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}" + (f"  -> {detail}" if detail else ""))


async def main() -> int:
    sid = f"orm-check-{uuid.uuid4().hex[:8]}"
    await init_db()

    try:
        conn = Tortoise.get_connection("default")

        # 1. 建表
        tables = await conn.execute_query_dict(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        names = {row["tablename"] for row in tables}
        check({"sessions", "reports"} <= names, "建表成功：sessions / reports 都存在", str(sorted(names)))

        # 2. 插入
        session = await SessionRecord.create(session_id=sid, jd_title="AI Agent 开发实习生")
        report = await ReportRecord.create(
            session=session,
            overall="基础扎实，追问深度不足，建议推进下一轮技术面。",
            overall_score=3.6,
            dimension_summary={"tech_depth": 3.5, "project_authenticity": 4.0, "communication": 3.4},
            strengths=[{"point": "能讲清 checkpointer 的取舍", "evidence_quote": "状态放在库里，重启还能接着问"}],
            weaknesses=[
                {
                    "point": "指标设计只说结果没说口径",
                    "evidence_quote": "准确率大概百分之八十多",
                    "suggestion": "下次说清分母和标注方式",
                }
            ],
            gap_conclusion="缺 pgvector 与评测方法的实践。",
            next_steps=["补一个 pgvector 检索实验", "给准确率写清口径", "准备 2 分钟项目演示"],
            turns_used=8,
            skipped_dims=[],
        )
        check(report.id is not None, "插入：报告有自增主键", str(report.id))

        # 3. JSONB 往返
        got = await ReportRecord.get(id=report.id)
        check(
            got.dimension_summary == {"tech_depth": 3.5, "project_authenticity": 4.0, "communication": 3.4},
            "读回：dimension_summary 的 JSONB 结构与内容一致",
            str(got.dimension_summary),
        )
        check(
            got.strengths[0]["evidence_quote"] == "状态放在库里，重启还能接着问",
            "读回：中文与嵌套结构没被搞乱",
            str(got.strengths),
        )
        check(len(got.next_steps) == 3, "读回：next_steps 是 3 条", str(got.next_steps))

        # 4. 外键
        rel = await ReportRecord.get(id=report.id).prefetch_related("session")
        check(rel.session.session_id == sid, "外键：能从报告顺着取到面试记录")

        # 5. 列类型
        cols = await conn.execute_query_dict(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='reports' AND column_name IN ('dimension_summary','strengths','next_steps')"
        )
        types = {row["column_name"]: row["data_type"] for row in cols}
        check(
            types and all(t == "jsonb" for t in types.values()),
            "列类型：三个字段都是 jsonb",
            str(types),
        )

        # 6. 聚合（业务表的存在理由）
        await ReportRecord.create(
            session=session, overall="第二条样本", overall_score=4.2, turns_used=10
        )
        rows = await ReportRecord.filter(session_id=sid).values("overall_score", "turns_used")
        avg = sum(r["overall_score"] for r in rows) / len(rows)
        check(len(rows) == 2 and abs(avg - 3.9) < 1e-6, "聚合：能按行取数并算平均分", f"n={len(rows)} avg={avg}")

        # 7. 级联删除
        await SessionRecord.filter(session_id=sid).delete()
        left = await ReportRecord.filter(session_id=sid).count()
        check(left == 0, "外键级联：删了面试记录，报告跟着删", f"剩 {left} 条")

    finally:
        # 兜底清理：即使中间 FAIL 也别在库里留垃圾
        await ReportRecord.filter(session_id=sid).delete()
        await SessionRecord.filter(session_id=sid).delete()
        await close_db()

    print(f"\n结果：{len(PASSED)}/{len(PASSED) + len(FAILED)} 通过。")
    if FAILED:
        print("失败项：" + "；".join(FAILED))
        return 1
    print("全绿。持久层（Tortoise）可以接进 API 了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
