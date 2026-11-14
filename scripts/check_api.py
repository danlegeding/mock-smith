"""端到端验收：对着已经跑起来的 API 打一遍完整面试。

前置：数据库容器在跑 + uvicorn 已启动
    python -m uvicorn src -.app:app --port 8010
跑法：
    python scripts/check_api.py                      # 默认 http://127.0.0.1:8010
    python scripts/check_api.py --base-url http://127.0.0.1:8000

和 test_schemas.py / check_parse.py / check_orm.py 的区别：这个查的是"接口层接线对不对"，
不查模型质量——模型输出是好是坏，看报告自己判断。
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent

FAKE_ANSWERS = [
    "我用 LangChain 的 RetrievalQA 把检索和问答串起来，向量库用 Chroma，prompt 里塞 top3 文档",
    "接口加了 Pydantic 校验和统一异常处理，uvicorn 起服务，超时设了 30 秒",
    "先拆成规划、检索、回复三步，每步一个函数，中间用状态对象传数据",
    "客服项目主要是我做的意图识别和检索部分，数据库表是同组同学建的",
    "了解过一点，没实际做过",
    "先把日志看一遍，再看是不是数据库慢查询",
]

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    # 不用 ✓/✗：Windows 控制台默认 GBK，输出重定向时会直接 UnicodeEncodeError 崩掉
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    parser = ArgumentParser(description="对运行中的 API 做端到端验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--jd", default=str(ROOT / "data" / "jds" / "01-ai-agent-intern.md"))
    parser.add_argument("--resume", default=str(ROOT / "data" / "resumes" / "sample-02-medium.md"))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    # trust_env=False：本机回环地址直连，别被环境里的 HTTP_PROXY 拿去回 502
    with httpx.Client(base_url=base, timeout=600.0, trust_env=False) as client:
        # ---- 1. 探活
        health = client.get("/health")
        check("GET /health", health.status_code == 200 and health.json()["status"] == "ok")

        # ---- 2. 开一场面试：应该立刻返回第一题
        created = client.post(
            "/sessions",
            json={
                "jd_text": Path(args.jd).read_text(encoding="utf-8"),
                "resume_text": Path(args.resume).read_text(encoding="utf-8"),
            },
        )
        check("POST /sessions 200", created.status_code == 200, str(created.status_code))
        if created.status_code != 200:
            print(created.text[:800])
            return 1
        first = created.json()
        session_id = first["session_id"]
        check("返回 type=question", first["type"] == "question", first["type"])
        check("turn_index 从 0 开始", first["turn_index"] == 0, str(first["turn_index"]))
        check("第一题有题干", bool(first["question"]["text"]))
        print(f"  第 1 题 [{first['question']['dimension']}] {first['question']['text']}")

        # ---- 2.5 进行中的会话：transcript 要能给出「还没答的那题」，记录页靠它恢复面试
        mid = client.get(f"/sessions/{session_id}/transcript")
        check("进行中会话 /transcript 200", mid.status_code == 200, str(mid.status_code))
        if mid.status_code == 200:
            body = mid.json()
            check("刚开面时 turns 为空", body.get("turns") == [], str(len(body.get("turns") or [])))
            check(
                "pending_question 就是第一题",
                (body.get("pending_question") or {}).get("text") == first["question"]["text"],
            )

        # ---- 3. 一轮轮回答，直到拿到报告
        current = first
        turn_no = 1
        answered = 0
        while current["type"] == "question" and turn_no <= len(FAKE_ANSWERS) + 2:
            payload = {"session_id": session_id, "answer": FAKE_ANSWERS[(turn_no - 1) % len(FAKE_ANSWERS)]}
            resp = client.post(f"/sessions/{session_id}/answer", json=payload)
            check(f"POST answer 第{turn_no}轮 200", resp.status_code == 200, str(resp.status_code))
            if resp.status_code != 200:
                print(resp.text[:800])
                return 1
            answered += 1
            current = resp.json()
            if current["type"] == "question":
                print(f"  第 {current['turn_index'] + 1} 题 [{current['question']['dimension']}] {current['question']['text']}")
            turn_no += 1

        check("面试以 report 收尾", current["type"] == "report", current["type"])
        report = current["report"] or {}

        # ---- 4. 报告结构
        check("报告有结论", bool(report.get("overall")))
        check("维度均分非空", bool(report.get("dimension_summary")))
        check("下一步正好 3 条", len(report.get("next_steps") or []) == 3)
        check("亮点/弱项都带证据", all(
            item.get("evidence_quote")
            for key in ("strengths", "weaknesses")
            for item in (report.get(key) or [])
        ))

        # ---- 5. 报告已落库，走数据库这条路再取一次
        got = client.get(f"/sessions/{session_id}/report")
        check("GET /report 200", got.status_code == 200, str(got.status_code))
        check("落库报告与返回值一致", got.status_code == 200 and got.json()["overall"] == report.get("overall"))

        # ---- 5.5 问答记录（前端「④ 记录页」用的就是这个接口）
        transcript = client.get(f"/sessions/{session_id}/transcript")
        check("GET /transcript 200", transcript.status_code == 200, str(transcript.status_code))
        turns = transcript.json().get("turns") or [] if transcript.status_code == 200 else []
        check("记录里有本场问答", len(turns) == answered, f"{len(turns)} 轮记录 vs {answered} 次作答")
        check("每轮都能定位到题目", all(t.get("question", {}).get("text") for t in turns))

        # ---- 6. 结束后的边界行为
        after = client.post(f"/sessions/{session_id}/answer", json={"session_id": session_id, "answer": "x"})
        check("结束后再回答 → 409", after.status_code == 409, str(after.status_code))
        missing = client.get("/sessions/not-exist/report")
        check("不存在的会话 → 404", missing.status_code == 404, str(missing.status_code))

        # ---- 7. 列表里能看到这一场
        listing = client.get("/sessions?limit=20")
        check("GET /sessions 200", listing.status_code == 200)
        check("列表包含本场", any(item["session_id"] == session_id for item in listing.json()))

    failed = [name for name, ok, _ in checks if not ok]
    print()
    if failed:
        print(f"结果：{len(checks) - len(failed)}/{len(checks)} 通过，失败：{', '.join(failed)}")
        return 1
    print(f"结果：{len(checks)}/{len(checks)} 全绿，session={session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
