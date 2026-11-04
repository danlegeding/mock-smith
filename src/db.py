"""数据库：连接池 + checkpointer + 自检。

整个进程只有一个连接池。checkpointer 用它把图的状态（每一轮问答）
落到 Postgres 里，所以进程重启/断线后还能接着聊——这就是
「断线续面」的实现点，thread_id 直接复用 session_id。

注意分工：本文件只管**图的状态**（psycopg 同步池）。
我们自己的业务表（sessions / reports）在 `src/orm.py` + `src/orm_models.py`，
用的是 Tortoise ORM + asyncpg，另一条连接，别在这里塞业务表。
"""

from __future__ import annotations

import atexit

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.config import settings

_pool: ConnectionPool | None = None


# 全局只创建一个连接池
def get_pool() -> ConnectionPool:
    """第一次调用时创建，之后复用同一个。

    坑：autocommit=True 必须带。实测不带它：写入当场成功、同一条连接也读得到，
        但换一条连接查就是 0 行——因为从头到尾没有 commit，连接一关就回滚。
        症状不是报错，而是「重启后状态全没了」，属于最难查的那类。
        row_factory=dict_row 是给我们自己按列名取值的（LangGraph 内部会自己设）。
    """
    global _pool
    if _pool is None:
        pool = ConnectionPool(
            conninfo=settings.database_url,
            kwargs={"autocommit": True, "row_factory": dict_row},
            min_size=2,
            max_size=10,
        )
        try:
            # 连不上就现在炸，别等到第一个请求才炸
            pool.wait(timeout=10)
        except Exception:
            # 关键：初始化失败必须把池关掉并复位，
            # 否则 _pool 留着这个半死不活的池，
            # 下一次调用会抛 PoolClosed（一个很难懂的错）。
            pool.close()
            raise
        _pool = pool
    return _pool


def close_pool() -> None:
    """进程退出时关掉。FastAPI 的 lifespan 里调。"""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def make_checkpointer() -> PostgresSaver:
    """用上面的池子造一个 checkpointer。

    坑：返回之前必须先调一次 .setup()，它会自动建 3 张表。
        setup() 重复调用是安全的，所以每次启动都调没关系。
    """
    saver = PostgresSaver(get_pool())
    saver.setup()
    return saver


def check_db() -> dict:
    """自检脚本的全部逻辑：
    1) 能连上并 SELECT 1
    2) 查 pg_extension 里有没有 vector
    3) 查 checkpoints 表存在不存在
    返回 {"ok": bool, "vector": bool, "checkpoint_tables": bool}
    """
    result: dict = {"ok": False, "vector": False, "checkpoint_tables": False}
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
            result["vector"] = (
                conn.execute(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                ).fetchone()
                is not None
            )
            result["checkpoint_tables"] = (
                conn.execute(
                    "SELECT 1 FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename = 'checkpoints'"
                ).fetchone()
                is not None
            )
            result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - 自检脚本就该把错误吞成返回值
        result["error"] = str(exc)
    return result


# 脚本/测试跑完自动收尾。不注册的话，进程退出时池子里的线程停不下来，
# 控制台会刷一堆 "couldn't stop thread ... within 5.0 seconds"。
atexit.register(close_pool)
