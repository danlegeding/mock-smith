"""节点 1：parse_inputs —— 把 JD / 简历原文解析成结构化 profile。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.graph.state import InterviewState
from src.llm import call_json
from src.model import JDProfile, ResumeProfile

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def render_prompt(name: str, **values: str) -> str:
    """读出 prompts/<name> 并把 {{占位符}} 替换成实际内容，返回渲染好的提示词。"""
    text = (PROMPT_DIR / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def extract_jd_profile(jd_text: str) -> JDProfile:
    """从 JD 原文里抽出结构化信息，返回 JDProfile。"""
    return call_json(
        JDProfile,
        system=render_prompt("parse_jd.md", jd_text=jd_text),
        user="请按上面的规则解析这份 JD。",
        temperature=0,
    )


def extract_resume_profile(resume_text: str) -> ResumeProfile:
    """从简历原文里抽出结构化信息，返回 ResumeProfile。"""
    return call_json(
        ResumeProfile,
        system=render_prompt("parse_resume.md", resume_text=resume_text),
        user="请按上面的规则解析这份简历。",
        temperature=0,
    )


def parse_inputs(state: InterviewState) -> dict[str, Any]:
    """LangGraph 节点函数：把 state 里的 JD / 简历原文解析成两个 profile。"""
    jd_profile = extract_jd_profile(state["jd_text"])
    resume_profile = extract_resume_profile(state["resume_text"])
    return {
        "jd_profile": jd_profile.model_dump(mode="json"),
        "resume_profile": resume_profile.model_dump(mode="json"),
    }
