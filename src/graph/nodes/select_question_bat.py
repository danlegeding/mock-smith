# from __future__ import annotations
#
# from typing import Any
#
# from model import QuestionPlan
#
# def _pick_question(
#     plan:list[dict[str,Any]],
#     turns:list[dict[str,Any]],
#     hint:int | None=None,
# )->dict[str,Any] | None:
#
#
# def select_question(state:dict[str,Any])->dict[str,Any]:
#     plan = state.get("question_plan",[])
#     turns = list(state.get("turns") or [])
#     question = _pick_question(plan,turns,state.get("next_difficulty"))
#     return {"current_question":question , "next_difficulty" : None}