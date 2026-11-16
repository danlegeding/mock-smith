"""面试会话：一个端点一个文件，这里只做聚合。"""

from fastapi import APIRouter

from src.api.routes.sessions import answer, create, listing, report, transcript

router = APIRouter()
for module in (create, answer, report, listing, transcript):
    router.include_router(module.router)

__all__ = ["router"]
