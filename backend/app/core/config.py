from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["local", "test", "production"] = "local"
    # Wall-clock timezone for dm_* business timestamps (created_at/updated_at). Postgres on the VM
    # runs in UTC, so these naive columns default to `now() AT TIME ZONE app_timezone` to store local
    # (VN) wall-clock time. Validated against pg_timezone_names before it ever reaches DDL.
    app_timezone: str = "Asia/Ho_Chi_Minh"
    database_url: str = "postgresql+psycopg://mdp_user:mdp_password@postgres:5432/mdp"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    jwt_secret_key: str = "change_me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    connection_secret_key: str = "change_me_connection_secret_key"
    postgres_password: str | None = None

    # --- API-key reveal (prompt 28, option ii) ---
    # APIKEY_ENC_KEY: secret used to derive the Fernet key that encrypts the API-key value AT REST so it
    # can be re-viewed later. Empty (default) = reveal feature OFF — keys stay hash-only, auth is
    # unaffected. Supplied via env only (never committed). apikey_view_password: the "level-2" friction
    # gate before a reveal — default "0000". NOTE: on a public repo this is friction, NOT real security.
    apikey_enc_key: str = ""
    apikey_view_password: str = "0000"

    # --- ora2pg Migration Dashboard v0.0 (additive; all from env, no hardcoded creds) ---
    # Oracle JDE source. Empty on environments that cannot reach Oracle (e.g. the VPS sandbox);
    # the dashboard fails gracefully and reports the connection error without crashing.
    oracle_host: str = ""
    oracle_port: str = "1521"
    oracle_sid: str = ""
    oracle_service_name: str = ""
    oracle_user: str = ""
    oracle_pwd: str = ""
    oracle_schema: str = "SYSTEM"
    # ora2pg container (compose service `ora2pg`, container_name overridable per project)
    ora2pg_container: str = "tipa_ora2pg"
    # Shared volume path where the backend writes the generated ora2pg.conf (== /config in ora2pg)
    ora2pg_shared_dir: str = "/opt/ora2pg"
    ora2pg_data_limit: int = 50000
    # Target schema in MDP's own postgres (design 1B: no separate DW, no FDW)
    ora2pg_target_schema: str = "mdp_staging"
    # Optional path to an EXTRA catalog JSON (same shape as jde_migrate_tables.json) appended to
    # the built-in table catalog at import time. Empty = built-in only. Used to register
    # environment-specific tables (e.g. sandbox test fixtures) WITHOUT editing the repo catalog.
    ora2pg_extra_catalog: str = ""

    # --- Source-count refresher (background estimate of Oracle source rows -> cache) ---
    # Default OFF; only turned on where Oracle is reachable (.63). The periodic loop only ever
    # does cheap ESTIMATE counts (Oracle stats); exact COUNT(*) runs on-demand via Verify.
    ora2pg_source_count_enabled: bool = False
    ora2pg_source_count_interval: int = 300  # seconds between estimate refreshes

    # --- Streaming (watermark-incremental) poll loop (prompt 27) ---
    # Loop ALWAYS runs (singleton); per-table `enabled` (Settings UI) is the control. This is now
    # only a MASTER kill-switch (default ON) for ops to globally pause.
    streaming_enabled: bool = True
    streaming_interval: int = 60  # loop tick seconds (per-table cadence = poll_interval_sec)

    # --- Matview auto-refresh loop (prompt 25) ---
    # Loop ALWAYS runs (singleton); per-model `matview_refresh_interval_sec` (Data Model UI) is the
    # control. MATVIEW_REFRESH_ENABLED is a MASTER kill-switch (default ON, re-checked each tick) for
    # ops to globally pause auto-refresh. `matview_refresh_interval` is only the idle re-check tick.
    matview_refresh_enabled: bool = True
    matview_refresh_interval: int = 30  # idle loop tick seconds (re-check for newly-due matviews)

    # --- Verify verdict tolerance (prompt 15) ---
    # A STREAMING-enabled table lags Oracle by the rows the loop has not yet pulled (live-lag, a few
    # rows for F0911/F4111). A tiny |source - target| diff is NOT a real MISMATCH, so the grid + Verify
    # treat it as MATCH when within the tolerance = max(rows, ratio * source). Non-streaming
    # (migrate-once) tables require an EXACT match (tolerance 0). Env-tunable; no per-job storage.
    streaming_verdict_tolerance_rows: int = 50
    streaming_verdict_tolerance_ratio: float = 0.0001  # 0.01%

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env != "production":
            return self

        invalid_settings: list[str] = []
        placeholder_secret_values = {
            "change_me",
            "change_me_connection_secret_key",
            "replace_with_very_long_random_secret_at_least_32_chars",
        }

        if not self.database_url:
            invalid_settings.append("DATABASE_URL is required")
        if not self.jwt_secret_key or self.jwt_secret_key in placeholder_secret_values:
            invalid_settings.append("JWT_SECRET_KEY must be set to a non-default value")
        elif len(self.jwt_secret_key) < 32:
            invalid_settings.append("JWT_SECRET_KEY must be at least 32 characters")
        if (
            not self.connection_secret_key
            or self.connection_secret_key in placeholder_secret_values
        ):
            invalid_settings.append("CONNECTION_SECRET_KEY must be set to a non-default value")
        elif len(self.connection_secret_key) < 32:
            invalid_settings.append("CONNECTION_SECRET_KEY must be at least 32 characters")
        if not self.cors_origins or all(
            "localhost" in origin or "127.0.0.1" in origin
            for origin in self.cors_origins
        ):
            invalid_settings.append("CORS_ORIGINS must include the production frontend origin")
        if self.postgres_password in {
            "mdp_password",
            "postgres",
            "password",
            "change_me",
            "replace_with_strong_password",
        }:
            invalid_settings.append("POSTGRES_PASSWORD must be changed from the default value")

        if invalid_settings:
            raise ValueError(
                "Invalid production configuration: " + "; ".join(invalid_settings)
            )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
