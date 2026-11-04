"""全局配置。所有配置只从这里进，别处不许硬编码。

以后要加并发数、超时、评测用的样本路径，都往 Settings 里加字段，
pydantic-settings 会自动去读同名环境变量。

字段名不必和 .env 里的键名一样：下面每个字段用 AliasChoices 列了几个
「可以被接受的名字」，谁先命中用谁。这样换供应商只要改 .env，不用改代码。
"""

from pathlib import Path

from pydantic import AliasChoices, Field
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

settings = Settings()
