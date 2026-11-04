"""确定性校验：判断一段引文是否真的出现在原文里。

这个文件存在的理由只有一个：**"模型说它核对过了"不算核对。**
agent 里那个 `verify_quote` 工具是给模型自查用的；出节点之后，代码还要用同一套规则
再核一遍。两道关都过，引文才算真。否则 evidence_quote 就成了"模型觉得它在原文里"。
"""

from __future__ import annotations

import re

#: 归一化时去掉的字符：空白、常见中英文标点、引号。
#: 目的：允许"标点不同 / 空格不同"，但不允许"换词 / 合并 / 脑补"。
_STRIP = re.compile(r"[\s\u3000，。、；：！？,.;:!?\"'`~—\-_/\\|()（）\[\]【】「」『』“”‘’…]")

#: 太短的引文没有核对价值（"我做过"这四个字到处都是）。
MIN_QUOTE_LEN = 4

#: 内部 id 的形态：s1 / s12 / p1 / p3（前后不能接字母数字，避免误伤 "p1x" 这种词）
_ID_TOKEN = re.compile(r"(?<![A-Za-z0-9_])[ps]\d{1,2}(?![A-Za-z0-9_])")


def strip_internal_ids(text: str) -> str:
    """把题干里的内部 id（s1/p1 这类）去掉，只留候选人能读懂的话。

    模型偶尔会把 id 念进问题里，实测出现过：
    「p1 这个问答助手里，文档怎么切分和召回的？」——候选人看到 p1 一脸问号。
    id 是给我们内部对账用的（evidence_ref 里已经有了），不该出现在候选人面前。
    """
    cleaned = _ID_TOKEN.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return re.sub(r"^[\s：:，,、。.]+", "", cleaned).strip()


def normalize(text: str) -> str:
    """去掉空白和标点，统一小写——只保留"字"本身。"""
    return _STRIP.sub("", text or "").lower()


def quote_in_answer(quote: str, answer: str) -> bool:
    """引文是否逐字出现在回答里（允许标点/空白/大小写差异）。"""
    normalized_quote = normalize(quote)
    if len(normalized_quote) < MIN_QUOTE_LEN:
        return False
    return normalized_quote in normalize(answer)


def verify_quote_detail(quote: str, answer: str) -> str:
    """给 agent 看的核对结果：命中或未命中，并说明原因。"""
    normalized_quote = normalize(quote)
    if len(normalized_quote) < MIN_QUOTE_LEN:
        return (
            f"未命中：引文太短（去掉标点后 {len(normalized_quote)} 字，"
            f"至少要 {MIN_QUOTE_LEN} 字才有核对意义）。请引用更长的原文片段。"
        )
    if normalized_quote in normalize(answer):
        return f"命中：这段引文确实在回答原文里（{len(normalized_quote)} 字）。可以用。"
    return (
        "未命中：回答原文里找不到这段文字。你可能改了字、合并了两句话，或者自己补了内容。"
        "请回到回答原文，复制一段连续的、原封不动的片段再核对。"
    )
