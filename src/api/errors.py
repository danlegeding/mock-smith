"""错误的唯一出口：所有异常都变成同一种 JSON 形状。

为什么单独一层：
1. 前端只写一套错误处理（`if (!resp.ok) show(resp.detail)`），不用为每个端点猜字段；
2. 500 的细节（模型栈、连接池异常）只在服务端日志里，不把内部信息漏给调用方；
3. 404/409 这些"预期内"的错误由 `APIError` 统一抛，端点里不用重复写 try/except。

统一后的形状：
    4xx: {"detail": "人能看懂的一句话"}
    422: {"detail": "入参校验失败", "errors": [{"loc": [...], "msg": "..."}]}
    500: {"detail": "服务内部错误（已记录日志）"}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class APIError(Exception):
    """预期内的业务错误：带状态码 + 给调用方看的一句话。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _json(status_code: int, payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload)


def register_error_handlers(app: FastAPI) -> None:
    """把四类异常挂到 app 上。顺序不重要，FastAPI 按异常类型精确匹配。"""

    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return _json(exc.status_code, {"detail": exc.detail})

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 保留 FastAPI 默认的 {"detail": ...} 形状，只是保证它一定走这个函数
        return _json(exc.status_code, {"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 422 默认的 body 很长很技术；收成一句话 + 精简后的字段列表
        errors = [
            {"loc": list(item.get("loc", [])), "msg": item.get("msg", "")} for item in exc.errors()
        ]
        return _json(422, {"detail": "入参校验失败", "errors": errors})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 兜底：任何没被上面接住的异常都在这里变成 500，并把真实栈留在服务端日志
        log.exception("未处理异常：%s %s", request.method, request.url.path)
        return _json(500, {"detail": "服务内部错误（已记录日志）"})
