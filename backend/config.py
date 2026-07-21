"""Environment-driven runtime configuration with production safety checks."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def normalize_database_url(value: str) -> str:
    """Make Railway/Heroku-style PostgreSQL URLs use SQLAlchemy's psycopg v3 driver."""
    value = value.strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def parse_origins(value: str) -> tuple[str, ...]:
    origins=[]
    for raw in value.split(","):
        origin=raw.strip().rstrip("/")
        if not origin: continue
        parsed=urlsplit(origin)
        if parsed.scheme not in {"http","https"} or not parsed.netloc or parsed.path not in {"","/"} or parsed.query or parsed.fragment:
            raise RuntimeError(f"ALLOWED_ORIGINS contains an invalid origin: {raw!r}")
        origins.append(origin)
    return tuple(dict.fromkeys(origins))


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str
    access_token_minutes: int
    refresh_token_days: int
    allowed_origins: tuple[str, ...]
    port: int
    forwarded_allow_ips: str
    crawl_user_agent: str
    crawl_timeout_seconds: int
    crawl_global_concurrency: int
    crawl_domain_rate_seconds: float
    max_consecutive_failures: int
    seed_demo_data: bool
    enable_inline_scheduler: bool
    openai_api_key: str | None
    openai_model: str

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    environment=os.getenv("ENVIRONMENT","development").lower()
    production=environment == "production"
    raw_database=os.getenv("DATABASE_URL","")
    raw_redis=os.getenv("REDIS_URL","")
    jwt_secret=os.getenv("JWT_SECRET","")
    allowed_origins=parse_origins(os.getenv("ALLOWED_ORIGINS","http://localhost:3000"))
    crawl_user_agent=os.getenv("CRAWL_USER_AGENT","")

    if production:
        if not raw_database or not normalize_database_url(raw_database).startswith("postgresql+psycopg://"):
            raise RuntimeError("DATABASE_URL must be an explicit PostgreSQL URL in production")
        if not raw_redis or not raw_redis.startswith(("redis://","rediss://")):
            raise RuntimeError("REDIS_URL must be an explicit redis:// or rediss:// URL in production")
        if len(jwt_secret) < 64:
            raise RuntimeError("JWT_SECRET must contain at least 64 characters in production")
        if not allowed_origins or any("*" in origin for origin in allowed_origins):
            raise RuntimeError("ALLOWED_ORIGINS must contain explicit frontend origins; '*' is forbidden in production")
        if not crawl_user_agent or "contact=" not in crawl_user_agent or "@" not in crawl_user_agent:
            raise RuntimeError("CRAWL_USER_AGENT must identify the crawler and include contact=<compliance email> in production")
        if _bool("SEED_DEMO_DATA",False):
            raise RuntimeError("SEED_DEMO_DATA cannot be enabled in production")

    database_url=normalize_database_url(raw_database or "sqlite:///./sales_intelligence.db")
    return Settings(
        environment=environment,
        database_url=database_url,
        redis_url=raw_redis or "redis://localhost:6379/0",
        jwt_secret=jwt_secret or "development-only-change-me-32-characters",
        jwt_algorithm="HS256",
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES","15")),
        refresh_token_days=int(os.getenv("REFRESH_TOKEN_DAYS","14")),
        allowed_origins=allowed_origins,
        port=int(os.getenv("PORT","8000")),
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS","*" if production else "127.0.0.1"),
        crawl_user_agent=crawl_user_agent or "Schneider-Sales-Intelligence/1.0 contact=compliance@example.com",
        crawl_timeout_seconds=int(os.getenv("CRAWL_TIMEOUT_SECONDS","30")),
        crawl_global_concurrency=int(os.getenv("CRAWL_GLOBAL_CONCURRENCY","4")),
        crawl_domain_rate_seconds=float(os.getenv("CRAWL_DOMAIN_RATE_SECONDS","2.0")),
        max_consecutive_failures=int(os.getenv("MAX_CONSECUTIVE_FAILURES","5")),
        seed_demo_data=False if production else _bool("SEED_DEMO_DATA",False),
        enable_inline_scheduler=False if production else _bool("ENABLE_INLINE_SCHEDULER",False),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL","gpt-4.1-mini"),
    )
