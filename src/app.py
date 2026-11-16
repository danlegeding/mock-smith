"""FastAPI 应用入口：只负责"组装"与"启动"，不写任何业务/路由细节。"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
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
    """启动时：建两套存储（checkpointer 表 + 业务表）；关闭时：按相反顺序释放。"""
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


def port_in_use(host: str, port: int) -> bool:
    """探测端口上是不是已经有服务在监听。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((host, port)) == 0


def find_listener_pid(port: int) -> str:
    """在 Windows 上查出占用端口的 PID，纯提示用；查不到就返回空字符串。"""
    try:
        output = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except Exception:  # noqa: BLE001 - 纯辅助信息，失败不影响主流程
        return ""
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
            return parts[4]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="启动模拟面试 Agent 后端")
    parser.add_argument("--host", default=os.getenv("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("APP_PORT", "8010")))
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("APP_RELOAD", "0") == "1",
        help="改代码自动重启（开发时用）",
    )
    args = parser.parse_args()

    if port_in_use(args.host, args.port):
        pid = find_listener_pid(args.port)
        print(f"\n端口 {args.port} 已被占用" + (f"（PID {pid}）" if pid else "") + "。")
        print("八成是上一次启动的服务没关。任选一种：")
        print(f"  1) 换端口启动： python src/app.py --port {args.port + 1}")
        print(f"  2) 关掉旧进程： taskkill /PID {pid or '<上面查到的PID>'} /F")
        print(f"  3) 查谁占着：   netstat -ano -p TCP | findstr :{args.port}")
        return 1

    import uvicorn

    # 用 import string 而不是传 app 对象：这样开启 reload 时 uvicorn 才能在子进程里重新导入
    uvicorn.run(
        "src.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(Path(__file__).resolve().parent)] if args.reload else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
