"""全局配置。所有配置只从这里进，别处不许硬编码。"""

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
        """把 DSN 里的 localhost 换成 127.0.0.1。"""
        return value.replace("@localhost:", "@127.0.0.1:").replace("@localhost/", "@127.0.0.1/")

settings = Settings()
