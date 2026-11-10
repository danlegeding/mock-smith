"""全局配置。所有配置只从这里进，别处不许硬编码。

以后要加并发数、超时、评测用的样本路径，都往 Settings 里加字段，
pydantic-settings 会自动去读同名环境变量。

字段名不必和 .env 里的键名一样：下面每个字段用 AliasChoices 列了几个
「可以被接受的名字」，谁先命中用谁。这样换供应商只要改 .env，不用改代码。
"""

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 在项目根目录（和 src/ 同级）。用绝对路径，
# 否则「从别的目录运行 python」时会找不到 .env，症状是 Settings() 报缺字段。
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # .env 里还有 POSTGRES_USER 等本类不认识的键，
        # 不设 ignore 会被 pydantic 判为非法字段直接报错。
        extra="ignore",
    )

    # ---------------- 数据库（db.py 用）
    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL"),
    )

    @field_validator("database_url")
    @classmethod
    def _force_ipv4_loopback(cls, value: str) -> str:
        """把 DSN 里的 localhost 换成 127.0.0.1。

        实测：Windows 上 localhost 会先解析到 ::1，而 Docker 发布的 [::]:5434
        能接受连接却不回包，于是 psycopg 连接池的 worker 线程一个个卡住，
        报 `PoolTimeout: pool initialization incomplete after 10 sec`；
        但单连接 `psycopg.connect("...@localhost:5434/...")` 又是通的，
        很容易误判成「数据库没起」或「密码错了」。换 127.0.0.1 后池 0.0 秒初始化完成。
        配置入口只有这一处，所以在这里统一纠正，别的进程不用各自踩一遍。
        """
        return value.replace("@localhost:", "@127.0.0.1:").replace("@localhost/", "@127.0.0.1/")

settings = Settings()
