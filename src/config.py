"""Configuration module for Snipara Server."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # Redis (for rate limiting) - optional, rate limiting disabled if not set
    redis_url: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS - comma-separated list of allowed origins
    # In production, this MUST be set explicitly (not "*")
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Rate limiting (per-minute, per-API-key)
    rate_limit_window: int = 60  # seconds
    rate_limit_requests: int = 60  # default fallback (used if plan unknown)

    # Plan-based rate limits (requests per minute)
    plan_rate_limits: dict[str, int] = {
        "FREE": 20,
        "PRO": 120,
        "TEAM": 300,
        "ENTERPRISE": 2000,
        "PARTNER": 5000,  # Partners/Integrators with heavy polling
    }

    # Demo key rate limiting (stricter, public key)
    demo_api_key_ids: str = ""  # comma-separated DB IDs of demo API keys
    demo_rate_limit_requests: int = 5  # requests per minute per IP for demo keys
    demo_rate_limit_window: int = 60  # seconds

    # IP-based rate limiting (public endpoints + authenticated FREE aggregate cap)
    ip_rate_limit_requests: int = 300  # requests per window per IP
    ip_rate_limit_window: int = 60  # seconds

    # Failed authentication throttling for /mcp and /v1 surfaces.
    # These routes intentionally skip broad IP limits for valid multi-agent traffic,
    # so failed credentials need their own stricter limiter.
    auth_failure_rate_limit_requests: int = 30
    auth_failure_rate_limit_window: int = 300  # seconds

    # Fail-closed: reject requests when Redis is unavailable in production
    rate_limit_fail_closed: bool = False

    # Security: Max JSON payload size for SSE params (in bytes)
    max_json_payload_size: int = 102400  # 100KB

    # Security: Regex execution timeout (in seconds)
    regex_timeout: float = 1.0

    # Security: Max regex pattern length
    max_regex_pattern_length: int = 500

    # Plan limits (queries per month)
    plan_limits: dict[str, int] = {
        "FREE": 100,
        "PRO": 5000,
        "TEAM": 20000,
        "ENTERPRISE": -1,  # unlimited
    }

    # Trash retention days per plan (0 = no trash, hard delete)
    trash_retention_days: dict[str, int] = {
        "FREE": 0,  # No trash - hard delete immediately
        "PRO": 7,  # 7-day trash retention
        "TEAM": 30,  # 30-day trash retention
        "ENTERPRISE": 90,  # 90-day trash retention
    }

    # Self-remote license key.
    # Local evaluation can run without a key. Production enterprise deployments
    # should set SNIPARA_LICENSE_REQUIRED=true and provide SNIPARA_LICENSE_KEY.
    snipara_license_key: str = ""
    snipara_license_required: bool = False

    # Optional commercial/admin surfaces. Disabled in the on-prem base package
    # unless a deployment explicitly enables them.
    enable_integrator_admin_api: bool = False

    # Internal API secret for server-to-server calls (e.g., web app → MCP server)
    # Used by reindex endpoint and other internal operations
    internal_api_secret: str = ""

    # Sentry error tracking (optional)
    sentry_dsn: str = ""

    # Environment name for Sentry
    environment: str = "development"

    # Embeddings
    preload_embeddings: bool = True
    embedding_service_url: str = ""
    embedding_service_local_only: bool = False
    embedding_service_timeout_overhead: float = 2.0

    # Memory V2 rollout flags
    memory_v2_dual_write: bool = False
    memory_v2_dual_read: bool = False
    memory_v2_primary_read: bool = True

    # Code graph rollout
    enable_code_ingestion: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as a list."""
        if self.cors_allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
