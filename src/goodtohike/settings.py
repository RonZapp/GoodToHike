"""Settings read from environment variables, or from a .env file."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ELEVATION_FILL = "hybrid"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GOODTOHIKE_",
        env_file=".env",
        env_ignore_empty=True,
    )

    database_url: str = "sqlite:///goodtohike.db"
    elevation_fill: str = DEFAULT_ELEVATION_FILL
    firms_map_key: SecretStr | None = None
