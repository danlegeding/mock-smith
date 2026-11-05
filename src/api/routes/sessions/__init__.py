"""面试会话：一个端点一个文件，这里只做聚合。

路径写在每个端点文件里（`/sessions`、`/sessions/{id}/answer` …），不在这一层加
`prefix=`。原因有两个：

1. 找端点时，URL 和函数在同一个文件里，不用跳两层去拼前缀；
2. FastAPI 0.162 加了个校验：父 router 带 prefix、子 router 再加空 path 会直接抛
   `FastAPIError: Prefix and path cannot be both empty`。与其记这个坑，不如让每个
   端点自己写全路径。

加新端点 = 新文件 + `route_modules` 里加一行，`routes/__init__.py` 不用改。
"""

from fastapi import APIRouter

from src.api.routes.sessions import answer, create, listing, report

router = APIRouter()
for module in (create, answer, report, listing):
    router.include_router(module.router)

__all__ = ["router"]
