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
    logfire_token: str = ""
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

    # Agent pack generation (OpenAI-compatible models via OpenRouter). Generation is
    # configured only when both the key and model are non-empty; see
    # ``generation_configured``.
    generation_model: str = "openai/gpt-5.6-terra"
    openrouter_api_key: str = ""

    # Per-user cap on billed draft generations, counted in a fixed one-hour
    # window (see ``services.rate_limit``). 0 or negative disables the cap.
    generation_rate_limit_per_hour: int = 10

    # Conversational practice (WF-16) shares the OpenRouter key with generation
    # but has its own model id, so chat can run a cheaper/faster model than
    # pack drafting without a code change. See ``practice_configured``.
    practice_model: str = "openai/gpt-5.6-terra"

    # Per-user cap on billed practice turns, in the same fixed one-hour window.
    # Higher than the generation cap: chat turns are frequent and cheap
    # relative to pack drafts. 0 or negative disables the cap.
    practice_rate_limit_per_hour: int = 60

    # Comma-separated email domains whose (non-guest) users are admins; see
    # ``habagou.authz.is_admin``. Matched exactly (no subdomains) and
    # case-insensitively against the part after the final ``@``.
    admin_email_domains: str = "mattjmcnaughton.com"

    # Comma-separated OpenRouter model ids admins may select for the AI chats
    # (pack generation and conversational practice), in display order. Each
    # feature's configured default model is always selectable and need not be
    # listed; see ``generation_model_ids`` / ``practice_model_ids``.
    admin_chat_models: str = "anthropic/claude-sonnet-5,minimax/minimax-m3"

    # Flips the code-defined feature-flag defaults
    # (``services.feature_flags.FLAG_DEFAULTS``) globally without a deploy of
    # code: comma-separated ``key:on`` / ``key:off`` entries. Unknown keys and
    # malformed entries are ignored. Note per-user database overrides (admin
    # API) still win over these defaults — this changes the default, it does
    # not force the flag for users holding an override.
    feature_flag_defaults: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @property
    def generation_configured(self) -> bool:
        """Whether agent pack generation can run (API key and model set)."""
        return bool(self.openrouter_api_key) and bool(self.generation_model)

    @property
    def practice_configured(self) -> bool:
        """Whether conversational practice can run (API key and model set)."""
        return bool(self.openrouter_api_key) and bool(self.practice_model)

    @property
    def admin_email_domain_set(self) -> frozenset[str]:
        """Parsed ``admin_email_domains``: lowercased, stripped, empties dropped."""
        return frozenset(
            domain.strip().lower()
            for domain in self.admin_email_domains.split(",")
            if domain.strip()
        )

    @property
    def feature_flag_default_map(self) -> dict[str, bool]:
        """Parsed ``feature_flag_defaults``: malformed entries dropped."""
        parsed: dict[str, bool] = {}
        for entry in self.feature_flag_defaults.split(","):
            key, separator, state = entry.strip().partition(":")
            key, state = key.strip(), state.strip().lower()
            if separator and key and state in ("on", "off"):
                parsed[key] = state == "on"
        return parsed

    def _selectable_model_ids(self, default: str) -> tuple[str, ...]:
        """The admin-selectable model ids for a feature: default first, deduped."""
        ordered = [default] if default else []
        for model_id in self.admin_chat_models.split(","):
            candidate = model_id.strip()
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return tuple(ordered)

    @property
    def generation_model_ids(self) -> tuple[str, ...]:
        """Model ids an admin may select for pack generation (allowlist)."""
        return self._selectable_model_ids(self.generation_model)

    @property
    def practice_model_ids(self) -> tuple[str, ...]:
        """Model ids an admin may select for conversational practice."""
        return self._selectable_model_ids(self.practice_model)


settings = Settings()
