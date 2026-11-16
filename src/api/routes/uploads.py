"""端点：上传 JD / 简历 PDF，转成 markdown 落到 `data/` 下。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile

from src.api.errors import APIError
from src.log import get_logger
from src.model import PdfUploadOut
from src.pdf2md import MAX_PDF_BYTES, ROOT, pdf_bytes_to_markdown, save_markdown

logger = get_logger(__name__)

router = APIRouter(tags=["上传"])


@router.post("/uploads/pdf", response_model=PdfUploadOut)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF 文件（JD 或简历）"),
    kind: Literal["jd", "resume"] = Form(..., description="jd=岗位描述，resume=简历"),
) -> PdfUploadOut:
    """把 PDF 转成 markdown 存进 `data/jds/` 或 `data/resumes/`，并把全文返回给前端。"""
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise APIError(400, "只支持 PDF：请上传 .pdf 文件（Word 可以先另存为 PDF）")

    raw = await file.read()
    if len(raw) > MAX_PDF_BYTES:
        raise APIError(413, f"文件太大（{len(raw) / 1024 / 1024:.1f} MB），上限 5 MB")

    try:
        markdown = pdf_bytes_to_markdown(raw, title=Path(filename).stem)
        saved = save_markdown(markdown, kind=kind, filename=filename)
    except ValueError as exc:
        # 转换失败是可解释的错误（扫描件/加密/坏文件），交给调用方看原因，不吞成 500
        raise APIError(400, str(exc)) from exc

    saved_path = saved.relative_to(ROOT).as_posix()
    logger.info("[upload] %s → %s（%d 字符）", filename, saved_path, len(markdown))
    return PdfUploadOut(
        kind=kind,
        filename=filename,
        saved_path=saved_path,
        chars=len(markdown),
        markdown=markdown,
    )
