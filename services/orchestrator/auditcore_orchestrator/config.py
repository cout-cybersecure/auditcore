from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDITCORE_", env_file=".env")

    db_dsn: str = "postgresql://auditcore:dev-only-change-me@localhost:5432/auditcore"
    gateway_url: str = "http://localhost:8001"
    default_tenant_id: str = "00000000-0000-0000-0000-000000000001"

    # Repo root → agents/ directory. Resolved relative to this file by default.
    agents_dir: Path = Path(__file__).resolve().parents[3] / "agents"

    # Per-agent budget; the gateway resolves the concrete model.
    budget_hint: str = "normal"
    privacy: str = "standard"


settings = Settings()
