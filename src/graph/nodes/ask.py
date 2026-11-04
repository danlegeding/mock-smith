"""节点 5：ask —— 把问题抛给用户，等回答回来。

这是整张图里最特殊的一个节点：它不"算"任何东西，而是**暂停**。

LangGraph 的 `interrupt()` 做的事：
1. 抛出当前节点的执行，把 state 存进 checkpointer（D1 建的 Postgres 表就是干这个的）；
2. 整个进程可以退出——面试中间关了电脑，明天再跑，从这一题接着问；
3. 用户回答后，用 `Command(resume=...)` 重新进入，`interrupt()` 的返回值就是
   resume 传进来的那个东西（这里是 `{"text": "..."}` 或 `{"skip": True}`）。

所以"多轮面试"不是靠一个 while 循环撑着的，而是靠**中断 + 检查点**。
这也是为什么 D1 要花时间把 checkpointer 接进 Postgres，而不是用内存版。
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from src.model import Question, Turn


def ask_question(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph 节点函数：提问 → 暂停等回答 → 把这一轮记录进 turns。

    Args:
        state: 当前面试状态，需要有 current_question 字段。

    Returns:
        dict: {"turns": [...], "current_question": None}，即新增一轮问答并清空当前题。
    """
    question = Question.model_validate(state["current_question"])

    # 这里的返回值只在本节点内有用，但它会在 resume 时被"重放"——
    # 所以 interrupt() 前面不能放有副作用的代码（写库、打日志），否则会执行两次。
    #
    # 坑：interrupt 的载荷必须把 Question 的字段**全部**带上，别手写字段清单。
    #     之前这里只挑了 text/dimension/difficulty/evidence_ref/kind 五个，
    #     追问（kind=followup）时丢了 anchor_quote，接口层 model_validate 就会报
    #     "kind=followup 时必须填 anchor_quote"——直接 500。用 model_dump 一次到底，
    #     以后 Question 加字段也不会漏。
    reply = interrupt(question.model_dump(mode="json"))

    # resume 允许两种写法：直接给字符串，或给 {"text": ...} / {"skip": True}
    if isinstance(reply, str):
        reply = {"text": reply}
    skipped = bool(reply.get("skip"))
    answer = "" if skipped else str(reply.get("text", "")).strip()

    turn = Turn(question=question, answer=answer, skipped=skipped)
    turns = list(state.get("turns") or [])
    turns.append(turn.model_dump(mode="json"))
    return {"turns": turns, "current_question": None}
