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
KIND_LABELS = {"opening": "主问题", "followup": "追问", "scenario": "情景题", "deep_dive": "深挖"}

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

        if st.button("重新开始一场", use_container_width=True):
            reset()
            st.rerun()

        st.divider()
        st.caption("页面：① 开面 → ② 面试 → ③ 报告")


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

    if st.button("开始面试", type="primary", use_container_width=True):
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
    submitted = col_submit.button("提交回答", type="primary", use_container_width=True)
    skipped = col_skip.button("跳过这题", use_container_width=True)

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

    st.divider()
    if st.button("再来一场", type="primary", use_container_width=True):
        reset()
        st.rerun()


# ---------------------------------------------------------------- 主流程
def main() -> None:
    init_state()
    sidebar()
    page = st.session_state["page"]
    if page == "开面":
        render_start()
    elif page == "面试":
        render_interview()
    else:
        render_report()


if __name__ == "__main__":
    main()
