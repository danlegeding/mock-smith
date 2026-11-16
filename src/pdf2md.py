"""PDF → Markdown：把上传的 JD / 简历 PDF 落成 `data/` 下的 `.md` 文件。"""

from __future__ import annotations

import io
import re
import time
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB：简历/JD 一般几百 KB，超过基本都是扫描件
MIN_MARKDOWN_CHARS = 80  # 少于这个字数基本等于"没抽到字"（扫描件/纯图片）

ROOT = Path(__file__).resolve().parent.parent  # 项目根目录
KIND_DIRS = {"jd": "data/jds", "resume": "data/resumes"}

_BULLET = re.compile(r"^[•●▪◦·※\*\-]\s*")
_PAGE_NUMBER = re.compile(r"^(第\s*\d+\s*页(\s*共\s*\d+\s*页)?|\d{1,3}\s*/\s*\d{1,3}|\d{1,3})$")
_DOT_LEADER = re.compile(r"(\.{5,}|…{2,}|·{5,})")  # 目录行：标题......4
_SECTION_NO = re.compile(r"^\d{1,2}(\.\d{1,2})*\s+\S")  # 1.1 软件项目概述
_CHINESE_NO = re.compile(r"^[一二三四五六七八九十]+[、.．]\s*\S")  # 一、整体要求
# 列表项开头：1） 2. （3） (4) a)
_LIST_START = re.compile(r"^(\d{1,2}[)）.、]|（\d{1,2}）|\(\d{1,2}\)|[a-zA-Z][)）])")
_END_PUNCT = "。！？!?；;：:、，,）)]】」》\"”"
_CJK = re.compile(r"[\u4e00-\u9fff]")
# 硬换行的前一行一般写满了；短行多半是表格单元格、标签，不该并进下一行
_WRAP_MIN_LEN = 25
# 简历/JD 里固定出现的节标题：短、独立成行，可以直接当二级标题
_SECTION_NAMES = {
    "岗位职责", "工作职责", "职位描述", "任职要求", "任职资格", "岗位要求",
    "技能要求", "加分项", "我们希望你", "你将负责", "工作内容",
    "个人信息", "教育背景", "教育经历", "专业技能", "技能清单",
    "项目经历", "项目经验", "实习经历", "工作经历", "校园经历",
    "获奖情况", "荣誉奖项", "自我评价", "个人总结", "证书",
}


def slugify(filename: str) -> str:
    """把上传的文件名变成安全的文件名：只留中英文数字和 `-_`，其余换成 `-`。"""
    stem = Path(filename).stem.strip()
    stem = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", stem, flags=re.UNICODE).strip("-")
    stem = re.sub(r"-{2,}", "-", stem)
    return stem[:60] or f"upload-{time.strftime('%Y%m%d-%H%M%S')}"


def _drop_repeated_lines(pages: list[list[str]]) -> list[list[str]]:
    """删掉每页重复出现的页眉页脚（只认每页首行/末行的重复，避免误删正文）。"""
    if len(pages) < 3:
        return pages

    first = Counter(lines[0] for lines in pages if lines)
    last = Counter(lines[-1] for lines in pages if lines)
    threshold = max(2, len(pages) // 2)
    repeated = {
        line
        for line, count in first.items()
        if count >= threshold and len(line) <= 40
    } | {
        line
        for line, count in last.items()
        if count >= threshold and len(line) <= 40
    }
    if not repeated:
        return pages
    return [[line for line in lines if line not in repeated] for lines in pages]


def _clean_lines(pages: list[list[str]]) -> list[str]:
    """逐行清洗：去页码 / 目录引导行、统一项目符号、去掉多余空白。"""
    lines: list[str] = []
    for page in _drop_repeated_lines(pages):
        for raw in page:
            line = raw.replace("\u3000", " ").replace("\xa0", " ").strip()
            if not line or _PAGE_NUMBER.match(line):
                continue
            if _DOT_LEADER.search(line):  # 目录行的点线，留着只会污染正文
                continue
            if _BULLET.match(line):
                line = "- " + _BULLET.sub("", line).strip()
            lines.append(re.sub(r"\s{2,}", " ", line))
    return lines


def _is_heading(line: str) -> bool:
    """判断一行是不是小标题（宁可少认，也不要把正文错标成标题）。"""
    stripped = line.strip()
    if stripped.startswith("#"):
        return True

    core = stripped.rstrip("：:")
    if core in _SECTION_NAMES:
        return True
    if len(stripped) > 22 or stripped.endswith(("。", "，", "；", "、")):
        return False

    # 「任职要求：」这类短标签：不能带逗号分号，否则就是一句话而不是标题
    if stripped.endswith(("：", ":")):
        return len(core) <= 14 and not any(char in core for char in "，,、。；")

    if _CHINESE_NO.match(stripped):
        return True
    if _SECTION_NO.match(stripped):
        # 「1.1 编写目的」算标题；「1 2026\10\20 某同学」这种表格行不算
        remainder = re.sub(r"^\d{1,2}(\.\d{1,2})*\s+", "", stripped)
        return len(remainder) <= 18 and not re.search(r"\d", remainder)
    return False


def _to_markdown_body(lines: list[str]) -> list[str]:
    """把清洗后的行拼成 markdown：标题加 `## `，被硬换行打断的句子接回去。"""
    out: list[str] = []
    for line in lines:
        if _is_heading(line):
            if line.startswith("#"):
                out.append(line)
            else:
                out.append("## " + line.rstrip("：:"))
            continue

        prev = out[-1] if out else ""
        can_join = (
            not line.startswith("- ")
            and not _LIST_START.match(line)  # 「1）…」是新的列表项，不能接上一行
            and len(prev) >= _WRAP_MIN_LEN
            and not prev.startswith(("- ", "# "))
            and prev[-1] not in _END_PUNCT
        )
        if can_join:
            joiner = "" if (_CJK.search(prev[-1]) or _CJK.search(line[0])) else " "
            out[-1] = prev + joiner + line
            continue
        out.append(line)
    return out


def pdf_bytes_to_markdown(data: bytes, *, title: str | None = None) -> str:
    """PDF 字节 → markdown 文本。抽不到文字时抛 ValueError（由接口层转 400）。"""
    if not data:
        raise ValueError("上传的文件是空的")

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pypdf 对坏文件抛的异常类型不稳定，统一收口
        raise ValueError(f"不是有效的 PDF 文件（{type(exc).__name__}）") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("PDF 有密码保护，请先解除密码再上传") from exc
        if reader.is_encrypted:
            raise ValueError("PDF 有密码保护，请先解除密码再上传")

    pages = [list((page.extract_text() or "").splitlines()) for page in reader.pages]
    body = _to_markdown_body(_clean_lines(pages))
    text = "\n\n".join(body).strip()

    if len(text) < MIN_MARKDOWN_CHARS:
        raise ValueError(
            "PDF 里几乎抽不到文字——多半是扫描件（图片型 PDF）。"
            "请上传可复制文字的版本，或先把 PDF 转成文字。"
        )

    heading = f"# {title.strip()}" if title and title.strip() else "# 上传的文档"
    return f"{heading}\n\n{text}\n"


def save_markdown(markdown: str, *, kind: str, filename: str) -> Path:
    """把转换结果写到 `data/jds/` 或 `data/resumes/`，返回落盘路径。"""
    if kind not in KIND_DIRS:
        raise ValueError(f"kind 只能是 {list(KIND_DIRS)}，收到 {kind!r}")

    target_dir = ROOT / KIND_DIRS[kind]
    target_dir.mkdir(parents=True, exist_ok=True)

    stem = slugify(filename)
    candidate = target_dir / f"{stem}.md"
    index = 2
    while candidate.exists():
        if candidate.read_text(encoding="utf-8") == markdown:
            return candidate
        candidate = target_dir / f"{stem}-{index}.md"
        index += 1

    candidate.write_text(markdown, encoding="utf-8")
    return candidate
