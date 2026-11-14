"""POST /sessions —— 开一场面试。

这个文件自带它需要的全部函数：入口 `create_session` + 它调用的 `_start_interview`。
只有真正被多个端点共用的原语（推进图、读快照、构造响应）才放在 `src/api/graph_io.py`。

图里跑：解析 JD/简历 → 查缺口 → 出题池 → 挑第一题，然后把第一题直接随响应返回。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src import crud
from src.api import graph_io
from src.api.deps import get_graph
from src.model import SessionCreate, TurnOut

router = APIRouter(tags=["面试"])


async def _start_interview(
    graph: Any,
    config: dict[str, Any],
    session_id: str,
    jd_text: str,
    resume_text: str,
) -> TurnOut:
    """开一场面试：跑图到第一题 → 建 session 行 → 返回第一题。

    为什么先建 session 行、后返回：图已经跑完第一题并且落进 checkpointer 了，
    这时 session 行必须存在，否则前端拿到的 session_id 在业务表里查不到。
    """
    await graph_io.invoke_graph(graph, config, {"jd_text": jd_text, "resume_text": resume_text})

    snapshot = await graph_io.read_snapshot(graph, config)
    jd_title = (snapshot.values.get("jd_profile") or {}).get("role_title", "")
    await crud.create_session(session_id, jd_title)
    return graph_io.build_turn_out(session_id, snapshot)


@router.post("/sessions", response_model=TurnOut, summary="开一场面试")
async def create_session(
    payload: SessionCreate,
    graph: Any = Depends(get_graph),
) -> TurnOut:
    """开一场面试，返回 `session_id` + 第一题。

    第一题随响应一起返回：前端少一次往返，而且「开面」和「推进」返回同一个
    `TurnOut` 模型，前端只需要写一套渲染逻辑。

    状态码用 200 而不是更"正确"的 201：`scripts/check_api.py` 把 200 写进了契约，
    改状态码得同时改验收脚本；等接口稳定了再统一升到 201。
    """
    session_id = graph_io.new_session_id()
    config = graph_io.config_for(session_id)
    return await _start_interview(
        graph, config, session_id, payload.jd_text, payload.resume_text
    )
