"""前端调后端的唯一出口：所有 HTTP 调用都收在这个文件里。"""

from __future__ import annotations

import os
from typing import Any

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8010")

# 开一场面试要跑「解析 JD/简历 + 匹配 + 出题」，串了 4~5 次模型调用，给足 10 分钟。
TIMEOUT_SECONDS = 600.0


def _trust_env() -> bool:
    """默认**不**相信环境里的代理变量。"""
    return os.getenv("API_TRUST_ENV", "0") == "1"


def _client() -> httpx.Client:
    """每次调用建一个短连接客户端：演示场景流量极小，不值得维护长连接。"""
    return httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_SECONDS, trust_env=_trust_env())


def health() -> dict[str, Any]:
    """探活：返回 `{"status": "ok", "db": {...}}`。"""
    with _client() as client:
        resp = client.get("/health")
        resp.raise_for_status()
        return resp.json()


def create_session(jd_text: str, resume_text: str) -> dict[str, Any]:
    """开一场面试，返回第一题（`TurnOut`：`session_id` / `type` / `turn_index` / `question`）。"""
    with _client() as client:
        resp = client.post("/sessions", json={"jd_text": jd_text, "resume_text": resume_text})
        resp.raise_for_status()
        return resp.json()


def submit_answer(session_id: str, answer: str) -> dict[str, Any]:
    """交一轮回答；`answer=""` 表示跳过。返回下一题或最终报告（`type` 字段区分）。"""
    with _client() as client:
        resp = client.post(f"/sessions/{session_id}/answer", json={"answer": answer})
        resp.raise_for_status()
        return resp.json()


def load_report(session_id: str) -> dict[str, Any]:
    """从数据库取已落库的最终报告（面试未结束时后端返回 409）。"""
    with _client() as client:
        resp = client.get(f"/sessions/{session_id}/report")
        resp.raise_for_status()
        return resp.json()


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """最近的历史会话：`[{session_id, jd_title, status, created_at}]`，按时间倒序。"""
    with _client() as client:
        resp = client.get("/sessions", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()


def load_transcript(session_id: str) -> dict[str, Any]:
    """一场面试的问答记录：`{session_id, status, turns: [...], pending_question}`。"""
    with _client() as client:
        resp = client.get(f"/sessions/{session_id}/transcript")
        resp.raise_for_status()
        return resp.json()


def upload_pdf(filename: str, content: bytes, kind: str) -> dict[str, Any]:
    """上传 JD / 简历 PDF：后端转成 markdown 存进 `data/`，返回"""
    with _client() as client:
        resp = client.post(
            "/uploads/pdf",
            files={"file": (filename, content, "application/pdf")},
            data={"kind": kind},
        )
        resp.raise_for_status()
        return resp.json()

