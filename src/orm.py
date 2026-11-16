"""业务表持久层：Tortoise ORM（异步）。"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from tortoise import Tortoise

from src.config import settings

# Tortoise 的 "apps" 配置里要写模型的导入路径，而不是类本身。
_MODELS_MODULE = "src.orm_models"


def _asyncpg_credentials() -> dict:
    """把 DATABASE_URL 拆成 asyncpg 要的 credentials 字典。"""
    url = urlsplit(settings.database_url)
    if not url.hostname:
        raise ValueError(f"DATABASE_URL 里没有 host，请检查 .env: {settings.database_url!r}")
    return {
        "host": url.hostname,
        "port": url.port or 5432,
        "user": unquote(url.username or ""),
        "password": unquote(url.password or ""),
        "database": url.path.lstrip("/"),
    }


def tortoise_config() -> dict:
    """Tortoise 的配置字典。写成函数是因为要用 settings（.env 可能在 import 之后才读）。"""
    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.asyncpg",
                "credentials": _asyncpg_credentials(),
            }
        },
        "apps": {
            "models": {
                "models": [_MODELS_MODULE],
                "default_connection": "default",
            }
        },
    }


async def init_db(*, global_fallback: bool = False) -> None:
    """初始化 ORM 并按需要建表。"""
    await Tortoise.init(config=tortoise_config(), _enable_global_fallback=global_fallback)
    await Tortoise.generate_schemas(safe=True)


async def close_db() -> None:
    """关闭 asyncpg 连接。脚本里放 finally，FastAPI 里放 lifespan 的收尾。"""
    await Tortoise.close_connections()
