"""节点 1：parse_inputs —— 把 JD / 简历原文解析成结构化 profile。

这是全项目第一个真正调用大模型的地方，也是唯一"读原文"的地方：
之后所有节点只用 profile（结构化的字段），不再碰原文。原因见 DESIGN.md §1：
把简历+JD 全文每轮重发进 prompt 会爆 token，而且模型会记住太多细节导致跑题。

三个函数都是薄壳：规则全在 prompts/*.md 里，这里只负责"读 prompt → 调模型"。
所以改 prompt 不用动代码，做 prompt 版本对比时也只换 .md 文件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.llm import call_json
from src.model import JDProfile, ResumeProfile

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def render_prompt(name: str, **values: str) -> str:
    """读出 prompts/<name> 并把 {{占位符}} 替换成实际内容，返回渲染好的提示词。

    模板放文件里而不是写成 Python 字符串：改 prompt 不用动代码，
    也方便以后做 prompt 版本对比（A/B 测同一段 prompt 的两版）。

    Args:
        name: prompt 文件名，如 "parse_jd.md"。
        **values: 占位符名 → 要填进去的文本，例如 jd_text="..."。

    Returns:
        str: 渲染完成的提示词文本，可直接当 system prompt 用。
    """
    text = (PROMPT_DIR / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def extract_jd_profile(jd_text: str) -> JDProfile:
    """从 JD 原文里抽出结构化信息，返回 JDProfile。

    Args:
        jd_text: 招聘启事原文。

    Returns:
        JDProfile: 岗位名、硬性要求、加分项、职责等字段（结构由 Pydantic 校验）。
    """
    return call_json(
        JDProfile,
        system=render_prompt("parse_jd.md", jd_text=jd_text),
        user="请按上面的规则解析这份 JD。",
        temperature=0,
    )


def extract_resume_profile(resume_text: str) -> ResumeProfile:
    """从简历原文里抽出结构化信息，返回 ResumeProfile。

    Args:
        resume_text: 简历原文。

    Returns:
        ResumeProfile: 技能、项目、经历、教育背景等字段。
    """
    return call_json(
        ResumeProfile,
        system=render_prompt("parse_resume.md", resume_text=resume_text),
        user="请按上面的规则解析这份简历。",
        temperature=0,
    )


def parse_inputs(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph 节点函数：把 state 里的 JD / 简历原文解析成两个 profile。

    只返回"要更新的字段"，不用把整个 state 还回去 —— LangGraph 会自己合并。
    存进 state 的是 dict（.model_dump(mode="json")），因为 state 要能进 checkpointer。

    Args:
        state: 至少包含 jd_text 和 resume_text 两个键的面试状态。

    Returns:
        dict: {"jd_profile": {...}, "resume_profile": {...}}。
    """
    jd_profile = extract_jd_profile(state["jd_text"])
    resume_profile = extract_resume_profile(state["resume_text"])
    return {
        "jd_profile": jd_profile.model_dump(mode="json"),
        "resume_profile": resume_profile.model_dump(mode="json"),
    }
