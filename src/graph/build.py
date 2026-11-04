"""把一个个节点拼成一张图 —— 这是生产代码，不是测试脚本。

FastAPI 起来之后调的就是这里；命令行演示（scripts/run_interview.py）调的也是这里。
所以这个文件永远不删，后面每加一个能力只会往里**加节点和边**。

现在的图（D7）：

    START → parse_inputs → match_gap → plan_questions → select_question ⇄ ask
                                                                ▲            │
                                                                │            ▼
                                                          evaluate_answer
                                                                │
                                                          decide_next
                                                          ╱    │    ╲
                                              select_question  ask   END

三个条件边是这个项目的"骨架"：
1. select_question 之后：有题问 → ask；没题了 → END
2. decide_next 之后：deepen → 直接问追问；next/升难度/降难度/换维度 → 回题池挑题；end → END
3. 循环本身也是条件边撑起来的（ask → evaluate_answer → decide_next → …）

为什么先建半张图：state 设计（字段够不够、能不能存进数据库）是最容易返工的地方，
先用几个节点跑通一次，比等到全部齐了才发现 state 缺字段便宜得多。
（D5 就踩过：question_plan 没写进 state，节点 return 了也被丢掉。）
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.graph.nodes.ask import ask_question
from src.graph.nodes.decide_next import decide_next_action
from src.graph.nodes.evaluate_answer import evaluate_answer
from src.graph.nodes.generate_report import generate_report
from src.graph.nodes.match_gap import match_gap
from src.graph.nodes.parse_inputs import parse_inputs
from src.graph.nodes.plan_questions import plan_questions
from src.graph.nodes.select_question import select_question
from src.graph.state import InterviewState
from src.model import DecideAction


def _route_after_select(state: InterviewState) -> str:
    """条件边：有下一题就去问，没有就收工。"""
    return "ask" if state.get("current_question") else "end"


def _route_after_decide(state: InterviewState) -> str:
    """条件边：按 decide_next 给的动作走。

    - end → 结束
    - deepen 且已经填好 current_question → 直接去问（追问）
    - 其余（next / raise_difficulty / lower_difficulty / switch_dim）→ 回题池挑
    """
    decision = state.get("decision") or {}
    action = decision.get("action")

    if action == DecideAction.END.value:
        return "end"
    if action == DecideAction.DEEPEN.value and state.get("current_question"):
        return "ask"
    return "select_question"


def build_graph() -> StateGraph:
    """拼图（还没编译）：定义节点 + 定义边。"""
    graph = StateGraph(InterviewState)

    # ① 注册节点：节点 id → 函数。id 是图里的标签（边、可视化、老 checkpoint 都用它），
    # 函数名则尽量写清"这个节点干了什么"，两者不必同名
    graph.add_node("parse_inputs", parse_inputs)
    graph.add_node("match_gap", match_gap)
    graph.add_node("plan_questions", plan_questions)
    graph.add_node("select_question", select_question)
    graph.add_node("ask", ask_question)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("decide_next", decide_next_action)
    graph.add_node("generate_report", generate_report)

    # ② 定义边：从哪走到哪。START/END 是框架给的虚拟起终点
    graph.add_edge(START, "parse_inputs")
    graph.add_edge("parse_inputs", "match_gap")
    graph.add_edge("match_gap", "plan_questions")
    graph.add_edge("plan_questions", "select_question")

    # ③ 条件边：select_question 之后有两岔路（没题可问就直接去收尾）
    graph.add_conditional_edges(
        "select_question",
        _route_after_select,
        {"ask": "ask", "end": "generate_report"},
    )

    # ④ 回答完先评分、再决策
    graph.add_edge("ask", "evaluate_answer")
    graph.add_edge("evaluate_answer", "decide_next")

    # ⑤ 决策后三岔路：追问 / 回题池挑下一题 / 收尾出报告
    graph.add_conditional_edges(
        "decide_next",
        _route_after_decide,
        {"ask": "ask", "select_question": "select_question", "end": "generate_report"},
    )

    # ⑥ 收尾：生成报告 → 结束
    graph.add_edge("generate_report", END)

    return graph


def build_persistent_graph() -> Any:
    """拼图 + 挂上 checkpointer（能存数据库、能断点续跑的那一版）。

    单独拆一个函数，是因为「要持久化」和「不要持久化」两种场景都要用：
    单元测试里用 build_graph()（不连库），跑真实面试用这个。
    """
    # 延迟导入：只有真的要用数据库时才建连接池，导入模块时不连库
    from src.db import make_checkpointer

    return build_graph().compile(checkpointer=make_checkpointer())
