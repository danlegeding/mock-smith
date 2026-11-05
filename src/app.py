"""FastAPI 应用入口：只负责"组装"与"启动"，不写任何业务/路由细节。

三种启动方式，效果完全一样（推荐第一种，省得记参数）：

    python src/app.py                 # 直接跑，端口/地址走默认值
    python -m src.app                 # 等价的模块方式
    uvicorn src.app:app --port 8010   # 老办法，CI/部署里常用

可调环境变量：APP_HOST（默认 127.0.0.1）、APP_PORT（默认 8010）、APP_RELOAD=1（改代码自动重启）。

结构：
    create_app()  建 app：lifespan（开库/关库）+ CORS + 错误处理 + 挂路由
    app           模块级实例，`uvicorn src.app:app` 用的就是它

为什么用工厂函数而不是在模块顶层东挂一点西挂一点：
- 测试可以 `create_app()` 造一个干净的 app（比如将来把 DB 换成 sqlite）；
- 组装顺序集中在一处，看这一个函数就知道"这个服务装了什么"。
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

# 允许 `python src/app.py` 直接跑：此时 sys.path[0] 是 src/，`import src.*` 会失败，
# 先把项目根塞进 sys.path（`python -m src.app` 和 uvicorn 方式则不需要）。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402  （必须在 sys.path 调整之后）
from fastapi.middleware.cors import CORSMiddleware

from src.api import api_router
from src.api.deps import get_graph
from src.api.errors import register_error_handlers
from src.db import close_pool
from src.orm import close_db, init_db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """启动时：建两套存储（checkpointer 表 + 业务表）；关闭时：按相反顺序释放。

    `global_fallback=True` 必须传：tortoise-orm 1.1.9 把连接存在 contextvar 里，
    lifespan 和请求处理不在同一个任务，不打开全局回退，端点里第一次查库就会报
    `RuntimeError: No TortoiseContext is currently active`。脚本单任务不需要，应用必须开。
    """
    await init_db(global_fallback=True)
    get_graph()
    try:
        yield
    finally:
        await close_db()
        close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="模拟面试 Agent",
        version="0.2.0",
        description=(
            "JD + 简历 → 多轮追问面试 → 可溯源评分报告。"
            "图跑在 LangGraph + Postgres checkpointer 上；业务表走 Tortoise ORM。"
        ),
        lifespan=lifespan,
    )

    # 前端（Streamlit）和浏览器不在同一个端口，跨域必须显式放行；
    # 部署时用环境变量 ALLOWED_ORIGINS 覆盖，别在代码里写死内网地址。
    origins = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8010"))
    # 用 import string 而不是传 app 对象：这样 APP_RELOAD=1 时 uvicorn 才能在子进程里重新导入
    uvicorn.run(
        "src.app:app",
        host=host,
        port=port,
        reload=os.getenv("APP_RELOAD", "0") == "1",
        reload_dirs=[str(Path(__file__).resolve().parent)] if os.getenv("APP_RELOAD") == "1" else None,
    )
