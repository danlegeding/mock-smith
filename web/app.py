"""模拟面试 Agent 的演示界面：开面 → 多轮问答 → 报告，三屏搞定。

运行（在项目根目录）：
    streamlit run web/app.py
需要后端先跑起来：
    uvicorn src.app:app --port 8010

设计原则：
- 所有状态放 `st.session_state`，刷新页面不丢；后端才是真相（checkpointer + reports 表），
  这里存的只是"当前要画什么"。
- 一个函数画一屏，屏幕之间靠 `page` 字段切换，避免 Streamlit 里到处 `rerun` 绕晕。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Streamlit 以脚本所在目录为工作目录，但我们要 import web/api_client.py，显式加一下更稳。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_client  # noqa: E402  （必须在 sys.path 改完之后 import）

ROOT = Path(__file__).resolve().parent.parent
JD_DIR = ROOT / "data" / "jds"
RESUME_DIR = ROOT / "data" / "resumes"

DIMENSION_LABELS = {
    "tech_depth": "技术深度",
    "project_authenticity": "项目真实性",
    "engineering_thinking": "工程思维",
    "communication": "沟通表达",
    "job_match": "岗位匹配",
}
DIFFICULTY_LABELS = {1: "基础", 2: "中等", 3: "深入"}
KIND_LABELS = {"opening": "主问题", "followup": "追问", "scenario": "情景题"}
STATUS_LABELS = {"active": "进行中", "finished": "已结束", "abandoned": "已放弃"}


# 注意：`st.set_page_config` 必须第一个 st 调用，但**不能写在模块顶层**——
# `python web/app.py` 直接跑时，模块顶层任何 st.* 都会在托管启动到 Streamlit 运行器之前
# 吐一行 `missing ScriptRunContext!` 的 WARNING。放到 main() 里既满足"第一个 st 调用"，也干净。
def configure_page() -> None:
    st.set_page_config(page_title="模拟面试 Agent", page_icon="🎤", layout="centered")


# ---------------------------------------------------------------- 状态管理
def init_state() -> None:
    """只在第一次打开页面时初始化，之后每次 rerun 都保留。"""
    defaults = {
        "page": "开面",
        "session_id": None,
        "turn": None,       # 最近一次 TurnOut
        "report": None,     # 最终报告（dict）
        "history": [],      # [{"question": {...}, "answer": "..."}]
        "records_transcript": None,  # 记录页：选中会话的问答记录
        "records_report": None,      # 记录页：选中会话的报告
        "records_pick": None,        # 记录页：selectbox 的 key 初值
        "page_before_records": "开面",  # 记录页「返回」要回到的那一屏
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset() -> None:
    """清空这场面试的所有前端状态，回到开面页。"""
    for key in ("session_id", "turn", "report"):
        st.session_state[key] = None
    st.session_state["history"] = []
    st.session_state["page"] = "开面"


def goto(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


def show_error(exc: Exception) -> None:
    """把后端的错误翻译成人话：HTTP 错误的 detail 字段是后端专门给前端看的。"""
    if isinstance(exc, api_client.httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
        except Exception:  # noqa: BLE001 - 不是 JSON 就退回原文
            detail = exc.response.text
        st.error(f"接口返回 {exc.response.status_code}：{detail}")
    elif isinstance(exc, api_client.httpx.RequestError):
        st.error(f"连不上后端（{api_client.BASE_URL}）：{exc}。请先启动 uvicorn src.app:app --port 8010")
    else:
        st.error(f"出错了：{exc}")


# ---------------------------------------------------------------- 侧边栏
def sidebar() -> None:
    with st.sidebar:
        st.title("🎤 模拟面试 Agent")
        st.caption("JD + 简历 → 多轮追问 → 可溯源评分报告")

        try:
            health = api_client.health()
            if health.get("status") == "ok":
                st.success("后端已连接")
            else:
                st.warning(f"后端探活异常：{health}")
        except Exception as exc:  # noqa: BLE001 - 侧边栏只做提示
            st.error("后端未连接")
            st.caption(str(exc))

        st.divider()
        st.write(f"**当前会话**：`{st.session_state['session_id'] or '未开始'}`")
        st.write(f"**已答轮数**：{len(st.session_state['history'])}")

        if st.button("重新开始一场", width="stretch"):
            reset()
            st.rerun()

        if st.button("📁 历史会话", width="stretch"):
            st.session_state["records_transcript"] = None
            st.session_state["records_report"] = None
            # 记下从哪一屏过来的，记录页的「返回」才知道回哪里（面试/报告/开面）
            current = st.session_state["page"]
            st.session_state["page_before_records"] = current if current in ("面试", "报告") else "开面"
            goto("记录")

        st.divider()
        st.caption("页面：① 开面 → ② 面试 → ③ 报告 → ④ 记录")


# ---------------------------------------------------------------- ① 开面
def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_start() -> None:
    st.header("① 开一场面试")
    st.write("选一份 JD 和一份简历（也可以直接手改文本），点开始后会依次跑：解析 → 缺口匹配 → 出题，再问第一题。")

    jd_files = sorted(JD_DIR.glob("*.md"))
    resume_files = sorted(RESUME_DIR.glob("*.md"))
    if not jd_files or not resume_files:
        st.error(f"没找到样本数据：{JD_DIR} / {RESUME_DIR}")
        return

    col_jd, col_resume = st.columns(2)
    with col_jd:
        jd_file = st.selectbox("JD 样本", jd_files, format_func=lambda p: p.name)
        jd_text = st.text_area("JD 内容", value=read_text(jd_file), height=260)
    with col_resume:
        resume_file = st.selectbox("简历样本", resume_files, format_func=lambda p: p.name)
        resume_text = st.text_area("简历内容", value=read_text(resume_file), height=260)

    if st.button("开始面试", type="primary", width="stretch"):
        with st.spinner("正在解析材料并出题，大约 20~60 秒…"):
            try:
                turn = api_client.create_session(jd_text, resume_text)
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
                return
        st.session_state["session_id"] = turn["session_id"]
        st.session_state["turn"] = turn
        st.session_state["history"] = []
        goto("面试")


# ---------------------------------------------------------------- ② 面试
def render_question_card(turn: dict) -> None:
    question = turn["question"]
    with st.container(border=True):
        st.markdown(f"### 第 {turn['turn_index'] + 1} 题")
        st.markdown(f"**{question['text']}**")
        meta = (
            f"{DIMENSION_LABELS.get(question['dimension'], question['dimension'])}"
            f" · 难度：{DIFFICULTY_LABELS.get(question['difficulty'], question['difficulty'])}"
            f" · {KIND_LABELS.get(question['kind'], question['kind'])}"
        )
        st.caption(meta)
        if question.get("anchor_quote"):
            st.caption(f"追问自你刚才说的：「{question['anchor_quote']}」")


def render_history() -> None:
    history = st.session_state["history"]
    if not history:
        return
    with st.expander(f"已答 {len(history)} 轮（点开看记录）"):
        for index, item in enumerate(history, start=1):
            question = item["question"]
            st.markdown(f"**{index}. [{DIMENSION_LABELS.get(question['dimension'], question['dimension'])}] {question['text']}**")
            st.markdown(f"> {item['answer'] or '（跳过）'}")


def render_interview() -> None:
    session_id = st.session_state["session_id"]
    turn = st.session_state["turn"]
    if not session_id or not turn:
        st.info("还没有进行中的面试。")
        if st.button("去开面"):
            goto("开面")
        return

    st.header("② 面试进行中")
    render_question_card(turn)
    render_history()

    answer = st.text_area(
        "你的回答（尽量给具体做法、数字和踩过的坑）",
        height=160,
        key=f"answer_{turn['turn_index']}",
        placeholder="例如：这块我用 FastAPI 写的，接口先定契约再补测试，上线后遇到并发写库的问题，加了唯一索引…",
    )

    col_submit, col_skip = st.columns([3, 1])
    submitted = col_submit.button("提交回答", type="primary", width="stretch")
    skipped = col_skip.button("跳过这题", width="stretch")

    if not (submitted or skipped):
        return

    text = answer.strip() if submitted else ""
    with st.spinner("评分中，大约 10~30 秒…"):
        try:
            result = api_client.submit_answer(session_id, text)
        except Exception as exc:  # noqa: BLE001
            show_error(exc)
            return

    st.session_state["history"].append({"question": turn["question"], "answer": text})
    st.session_state["turn"] = result

    if result["type"] == "report":
        st.session_state["report"] = result["report"]
        goto("报告")
    else:
        st.rerun()


# ---------------------------------------------------------------- ③ 报告
def render_report() -> None:
    report = st.session_state["report"]
    if not report:
        st.info("还没有报告，先把面试进行完。")
        return

    st.header("③ 面试报告")
    render_report_body(report)

    st.divider()
    if st.button("再来一场", type="primary", width="stretch"):
        reset()
        st.rerun()


def render_report_body(report: dict) -> None:
    """只画报告内容，不带标题和底部按钮——记录页复用同一套渲染，避免两份代码走偏。"""
    summary = report.get("dimension_summary") or {}
    if summary:
        average = sum(summary.values()) / len(summary)
        st.metric("综合评分（5 维均分）", f"{average:.2f} / 5")
        for key, score in summary.items():
            st.progress(min(score / 5.0, 1.0), text=f"{DIMENSION_LABELS.get(key, key)}：{score:.1f}")

    st.subheader("总体结论")
    st.write(report.get("overall", ""))

    strengths = report.get("strengths") or []
    if strengths:
        st.subheader("亮点")
        for item in strengths:
            st.markdown(f"- **{item['point']}**")
            st.caption(f"> {item['evidence_quote']}")

    weaknesses = report.get("weaknesses") or []
    if weaknesses:
        st.subheader("需要补的")
        for item in weaknesses:
            st.markdown(f"- **{item['point']}**")
            st.caption(f"> {item['evidence_quote']}")
            if item.get("suggestion"):
                st.caption(f"建议：{item['suggestion']}")

    if report.get("gap_conclusion"):
        st.subheader("JD 缺口结论")
        st.write(report["gap_conclusion"])

    st.subheader("下一步（按优先级）")
    for index, step in enumerate(report.get("next_steps") or [], start=1):
        st.markdown(f"{index}. {step}")


# ---------------------------------------------------------------- ④ 记录
def render_transcript(transcript: dict) -> None:
    """把 `turns` 画成一问一答；跳过的题、有评分的题分别标注。"""
    turns = transcript.get("turns") or []
    if not turns:
        st.info("这一场还没有问答记录（刚开面、还没答题）。")
        return
    for index, turn in enumerate(turns, start=1):
        question = turn.get("question") or {}
        dimension = DIMENSION_LABELS.get(question.get("dimension"), question.get("dimension", ""))
        st.markdown(f"**第 {index} 题** · {dimension} · {DIFFICULTY_LABELS.get(question.get('difficulty'), '')}")
        st.markdown(f"> {question.get('text', '')}")
        if turn.get("skipped"):
            st.caption("（跳过）")
        else:
            st.markdown(turn.get("answer") or "（未回答）")
            score = turn.get("score") or {}
            if score.get("valid") is not None:
                mark = "有证据" if score.get("valid") else "无证据"
                st.caption(f"评分 {score.get('avg', '-')} 分（{mark}）")


def _resume_state(session_id: str, transcript: dict) -> dict | None:
    """把「记录页拿到的 transcript」还原成面试页需要的 state。

    返回 None 表示这一场没有未回答的题（已结束或已出报告），没法继续。
    为什么只靠 transcript 就够：图的 state 一直在 checkpointer 里，
    端点已经把它摊成 `turns` + `pending_question`；前端不需要再问「下一题是什么」。
    """
    pending = transcript.get("pending_question")
    if not pending:
        return None
    history = [
        {
            "question": turn.get("question") or {},
            "answer": "" if turn.get("skipped") else (turn.get("answer") or ""),
        }
        for turn in (transcript.get("turns") or [])
    ]
    return {
        "session_id": session_id,
        "history": history,
        "turn": {
            "session_id": session_id,
            "type": "question",
            "question": pending,
            "turn_index": len(history),
        },
        "report": None,
    }


def render_records() -> None:
    """④ 历史会话：列表查 `sessions` 表，问答记录读图 state，报告查 `reports` 表。"""
    st.header("④ 会话记录")
    if st.button("← 返回", width="content"):
        goto(st.session_state.get("page_before_records") or "开面")
    st.caption("历史面试都在数据库里；这里只读不写，不会花模型钱。")

    try:
        records = api_client.list_sessions(limit=50)
    except Exception as exc:  # noqa: BLE001
        show_error(exc)
        return

    if not records:
        st.info("还没有面试记录。")
        if st.button("去开一场"):
            goto("开面")
        return

    st.dataframe(
        [
            {
                "时间": row.get("created_at", ""),
                "JD": row.get("jd_title", ""),
                "状态": STATUS_LABELS.get(row.get("status"), row.get("status", "")),
                "会话": row.get("session_id", ""),
            }
            for row in records
        ],
        width="stretch",
        hide_index=True,
    )

    labels = {
        row["session_id"]: f"{row.get('created_at', '')} · {row.get('jd_title', '')} · {STATUS_LABELS.get(row.get('status'), row.get('status'))}"
        for row in records
    }
    if st.session_state.get("records_pick") not in labels:
        st.session_state["records_pick"] = records[0]["session_id"]
    chosen = st.selectbox(
        "选一场查看",
        options=list(labels),
        format_func=lambda sid: labels[sid],
        key="records_pick",
    )
    status = next((row.get("status") for row in records if row["session_id"] == chosen), "active")

    if status == "active":
        if st.button("继续这场面试（按 checkpoint 恢复）", type="primary", width="stretch"):
            try:
                full = api_client.load_transcript(chosen)
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
            else:
                restored = _resume_state(chosen, full)
                if restored is None:
                    st.warning("这一场没有未回答的题（可能已经出报告了），用「查看报告」看结论。")
                else:
                    for key, value in restored.items():
                        st.session_state[key] = value
                    goto("面试")

    col_transcript, col_report = st.columns(2)
    with col_transcript:
        if st.button("查看问答记录", width="stretch"):
            try:
                st.session_state["records_transcript"] = api_client.load_transcript(chosen)
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
    with col_report:
        if st.button("查看报告", width="stretch", disabled=status != "finished"):
            try:
                st.session_state["records_report"] = api_client.load_report(chosen)
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
    if status != "finished":
        st.caption("这一场还没结束，报告要等面试跑完才有。")

    transcript = st.session_state.get("records_transcript")
    if transcript and transcript.get("session_id") == chosen:
        st.subheader("问答记录")
        render_transcript(transcript)

    report = st.session_state.get("records_report")
    if report:
        st.subheader("报告")
        render_report_body(report)


# ---------------------------------------------------------------- 主流程
def main() -> None:
    configure_page()
    init_state()
    sidebar()
    page = st.session_state["page"]
    if page == "开面":
        render_start()
    elif page == "面试":
        render_interview()
    elif page == "记录":
        render_records()
    else:
        render_report()


# ---------------------------------------------------------------- 启动方式
def _running_under_streamlit() -> bool:
    """判断当前脚本是不是被 `streamlit run` 拉起来的。

    在 Streamlit 运行时里，`get_script_run_ctx()` 有值；直接用 `python web/app.py`
    跑则没有——那种情况下每个 `st.*` 调用都会往终端吐一行
    `WARNING ... Thread 'MainThread': missing ScriptRunContext!`，刷屏且页面不显示。
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:  # noqa: BLE001 - 取不到上下文就当没在 Streamlit 里
        return False


def _port_in_use(host: str, port: int) -> bool:
    """探测端口是否已被监听（和 src/app.py 里同一个做法）。"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _launch_streamlit() -> int:
    """用 `python web/app.py` 启动时，把控制权交给 Streamlit 自己的运行器。

    这样后端(`python src/app.py`)和前端(`python web/app.py`)启动方式就对称了，
    也不用手动记 `-m streamlit run` 这串。
    """
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description="启动模拟面试前端（等价于 streamlit run web/app.py）")
    parser.add_argument("--server.port", dest="port", type=int, default=8501, help="端口，默认 8501")
    parser.add_argument("--server.address", dest="address", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    args, extra = parser.parse_known_args()

    if _port_in_use(args.address, args.port):
        print(f"端口 {args.port} 已被占用。八成是上一次的前端没关。任选一种：")
        print(f"  1) 换端口启动： python web/app.py --server.port {args.port + 1}")
        print(f"  2) 关掉旧进程： netstat -ano -p TCP | findstr :{args.port}  然后 taskkill /PID <PID> /F")
        return 1

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).resolve()),
        f"--server.address={args.address}",
        f"--server.port={args.port}",
        *extra,
    ]
    print("启动前端：" + " ".join(command[3:]))
    print(f"浏览器打开 http://{args.address}:{args.port}")
    return subprocess.call(command)


if __name__ == "__main__":
    if _running_under_streamlit():
        main()
    else:
        raise SystemExit(_launch_streamlit())
