"""业务表持久层：Tortoise ORM（异步）。

本进程里有两条独立的数据库通道，连的是同一个 Postgres 库，但职责不同：

1. `src/db.py` —— **psycopg 同步连接池**，只给 LangGraph 的 `PostgresSaver` 用。
   框架要的就是同步连接，表结构也由它的 `.setup()` 自己建（checkpoints 等 3 张表）。

2. `src/orm.py` —— **Tortoise ORM + asyncpg 异步连接**，管我们自己的业务表
   （`sessions` / `reports`，见 `src/orm_models.py`）。

为什么要两条而不是一条：
- checkpointer 存的是整个图的 state，形式是 JSONB blob。它能存，但**不能做 SQL 聚合**
  （"按维度均分排序"这种查询在 blob 里没法干）——所以业务上要单独建表。
- 表结构由我们声明（有外键、有索引、能改），而不是靠框架的 JSONB 一把梭。
- 同步池和异步池互不干扰：ORM 的 asyncpg 连接归 Tortoise 管，psycopg 池归 db.py 管。

用法（脚本里）：
    from src.orm import init_db, close_db
    await init_db()      # 连库 + 建表（safe=True，重复调用安全）
    try:
        ...              # await SessionRecord.create(...)
    finally:
        await close_db()
"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from tortoise import Tortoise

from src.config import settings

# Tortoise 的 "apps" 配置里要写模型的导入路径，而不是类本身。
_MODELS_MODULE = "src.orm_models"


def _asyncpg_credentials() -> dict:
    """把 DATABASE_URL 拆成 asyncpg 要的 credentials 字典。

    坑：不要把整条 DATABASE_URL 直接当 dsn 传进去。我们的密码里带 `@`，
         在 URL 里被写成 `%40`；交给 ORM 自己解析时，哪天换个驱动就想不起来为什么连不上。
         这里显式 unquote，一眼能看出来密码是解码过的。
    """
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
    """初始化 ORM 并按需要建表。

    generate_schemas(safe=True) = `CREATE TABLE IF NOT EXISTS`，重复调用安全，
    所以放在启动流程里每次都调没关系。

    坑（tortoise-orm 1.1.x）：上下文存在 contextvars 里，默认只对「初始化它的那个
        任务」可见。FastAPI 的 lifespan 跑在后台任务，请求处理在另一个任务——不传
        global_fallback=True，端点里第一次 `SessionRecord.create(...)` 就会报
        `RuntimeError: No TortoiseContext is currently active`。
        脚本是单任务，不需要开；所以默认 False，由调用方显式要求。

        这个开关每进程只能开一次（再 init 会抛 ConfigurationError），正好像
        「应用生命周期里只该初始化一次 ORM」的约束。
    """
    await Tortoise.init(config=tortoise_config(), _enable_global_fallback=global_fallback)
    await Tortoise.generate_schemas(safe=True)


async def close_db() -> None:
    """关闭 asyncpg 连接。脚本里放 finally，FastAPI 里放 lifespan 的收尾。"""
    await Tortoise.close_connections()
