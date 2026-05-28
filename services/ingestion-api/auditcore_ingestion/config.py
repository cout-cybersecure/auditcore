from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDITCORE_", env_file=".env")

    # Postgres
    db_dsn: str = "postgresql://auditcore:dev-only-change-me@localhost:5432/auditcore"

    # MinIO / S3
    s3_endpoint: str = "localhost:9000"
    s3_access_key: str = "auditcore"
    s3_secret_key: str = "dev-only-change-me"
    s3_secure: bool = False
    s3_bucket_raw: str = "auditcore-raw-evidence"

    # Default tenant for single-tenant Phase 1
    default_tenant_id: str = "00000000-0000-0000-0000-000000000001"

    # Limits
    max_bundle_bytes: int = 256 * 1024 * 1024  # 256 MiB


settings = Settings()
