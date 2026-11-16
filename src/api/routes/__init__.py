"""路由聚合：`app.py` 只挂一个 `api_router`，各业务模块自己管自己的路径。"""

from fastapi import APIRouter

from src.api.routes import health, sessions, uploads

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sessions.router)
api_router.include_router(uploads.router)

__all__ = ["api_router"]
