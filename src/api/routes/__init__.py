"""路由聚合：`app.py` 只挂一个 `api_router`，各业务模块自己管自己的路径。

这样加一个新模块（比如 `/evaluate`）只需要写一个新文件 + 这里 include 一行，
`app.py` 永远不用改。
"""

from fastapi import APIRouter

from src.api.routes import health, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sessions.router)

__all__ = ["api_router"]
