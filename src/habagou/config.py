"""Application configuration via environment variables."""

from pydantic import field_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine.url import make_url

# libpq/Neon query params that SQLAlchemy passes through as asyncpg connect()
# kwargs — asyncpg rejects them (TypeError: unexpected keyword argument).
_ASYNCPG_UNSUPPORTED_QUERY_KEYS = ("channel_binding", "sslmode")


def normalize_database_url(url: str) -> str:
    """Rewrite Neon/libpq-style URLs for SQLAlchemy asyncpg.

    - ``postgresql://`` / ``postgres://`` → ``postgresql+asyncpg://``
    - ``sslmode=`` → ``ssl=`` (asyncpg rejects ``sslmode``)
    - drop ``channel_binding`` (Neon default; asyncpg rejects it)
    """
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+asyncpg")

    query = dict(parsed.query)
    ssl_value: str | None = None
    raw_ssl = query.get("ssl")
    if raw_ssl is not None:
        ssl_value = raw_ssl[0] if isinstance(raw_ssl, (list, tuple)) else raw_ssl
    if "sslmode" in query:
        raw_mode = query["sslmode"]
        ssl_value = raw_mode[0] if isinstance(raw_mode, (list, tuple)) else raw_mode

    parsed = parsed.difference_update_query(list(_ASYNCPG_UNSUPPORTED_QUERY_KEYS))
    if ssl_value is not None and "ssl" not in dict(parsed.query):
        parsed = parsed.update_query_dict({"ssl": ssl_value})

    return parsed.render_as_string(hide_password=False)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    log_level: str = "INFO"
    log_format: str = "json"
    host: str = "0.0.0.0"
    port: int = 8000

    otel_exporter_otlp_endpoint: str = ""
    require_frontend: bool = False

    database_url: str = "postgresql+asyncpg://localhost:5432/habagou"

    session_secret_key: str = ""
    session_cookie_secure: bool = False
    oidc_provider: str = "keycloak"
    oidc_scopes: str = "openid profile email"
    oidc_issuer: str = ""
    oidc_metadata_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""

    # Agent pack generation (OpenAI models via OpenRouter). Generation is
    # configured only when both the key and model are non-empty; see
    # ``generation_configured``.
    generation_model: str = "openai/gpt-5-mini"
    openrouter_api_key: str = ""

    # Per-user cap on billed draft generations, counted in a fixed one-hour
    # window (see ``services.rate_limit``). 0 or negative disables the cap.
    generation_rate_limit_per_hour: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @property
    def generation_configured(self) -> bool:
        """Whether agent pack generation can run (API key and model set)."""
        return bool(self.openrouter_api_key) and bool(self.generation_model)


settings = Settings()
