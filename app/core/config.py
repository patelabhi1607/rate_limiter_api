from functools import lru_cache
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://rate_limiter:rate_limiter@localhost:5432/rate_limiter"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_fail_open: bool = True
    redis_max_connections: int = 20
    redis_socket_timeout: float = 0.5

    # Proxy trust
    trusted_proxy_hops: int = 1

    # Defaults
    default_limit: int = 100
    default_window_seconds: int = 60
    default_algorithm: Literal["token_bucket", "sliding_window", "fixed_window", "leaky_bucket"] = "sliding_window"

    # Admin
    admin_api_key: str = "change-me-in-production"

    # Observability
    log_level: str = "INFO"
    metrics_enabled: bool = True

    # Skip list — these paths are never rate limited
    skip_paths: list[str] = ["/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/static"]

    # Static whitelists / blacklists (comma-separated, loaded at startup)
    whitelist_ips: str = ""
    blacklist_ips: str = ""

    # Postgres (used by docker-compose; DATABASE_URL takes precedence in app)
    postgres_user: str = "rate_limiter"
    postgres_password: str = "rate_limiter"
    postgres_db: str = "rate_limiter"

    @field_validator("default_algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        allowed = {"token_bucket", "sliding_window", "fixed_window", "leaky_bucket"}
        if v not in allowed:
            raise ValueError(f"algorithm must be one of {allowed}")
        return v

    def get_whitelist_ips(self) -> list[str]:
        return [ip.strip() for ip in self.whitelist_ips.split(",") if ip.strip()]

    def get_blacklist_ips(self) -> list[str]:
        return [ip.strip() for ip in self.blacklist_ips.split(",") if ip.strip()]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
