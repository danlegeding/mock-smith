"""把一个个节点拼成一张图 —— 这是生产代码，不是测试脚本。"""

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
    """条件边：按 decide_next 给的动作走。"""
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

    # 节点 id 是图里的标签（边、可视化、老 checkpoint 都用它），可以和函数名不同
    graph.add_node("parse_inputs", parse_inputs)
    graph.add_node("match_gap", match_gap)
    graph.add_node("plan_questions", plan_questions)
    graph.add_node("select_question", select_question)
    graph.add_node("ask", ask_question)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("decide_next", decide_next_action)
    graph.add_node("generate_report", generate_report)

    # 固定边：解析 → 匹配 → 出题 → 选题
    graph.add_edge(START, "parse_inputs")
    graph.add_edge("parse_inputs", "match_gap")
    graph.add_edge("match_gap", "plan_questions")
    graph.add_edge("plan_questions", "select_question")

    # 条件边：选题后没题可问就直接去收尾
    graph.add_conditional_edges(
        "select_question",
        _route_after_select,
        {"ask": "ask", "end": "generate_report"},
    )

    # 回答后先评分、再决策
    graph.add_edge("ask", "evaluate_answer")
    graph.add_edge("evaluate_answer", "decide_next")

    # 条件边：追问 / 回题池 / 收尾
    graph.add_conditional_edges(
        "decide_next",
        _route_after_decide,
        {"ask": "ask", "select_question": "select_question", "end": "generate_report"},
    )

    # 收尾
    graph.add_edge("generate_report", END)

    return graph


def build_persistent_graph() -> Any:
    """拼图 + 挂上 checkpointer（能存数据库、能断点续跑的那一版）。"""
    # 延迟导入：真要连库时才建连接池
    from src.db import make_checkpointer

    return build_graph().compile(checkpointer=make_checkpointer())
