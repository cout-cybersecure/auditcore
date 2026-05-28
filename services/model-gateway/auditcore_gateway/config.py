from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDITCORE_GATEWAY_", env_file=".env")

    # Path to the routing.yaml relative to repo root or absolute.
    routing_config: Path = Path(__file__).resolve().parents[1] / "routing.yaml"

    # Provider credentials (read lazily; only required when routed to).
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # Local model endpoint (e.g. llama.cpp server, vLLM, Ollama).
    local_endpoint: str = "http://localhost:11434"

    # Bind
    host: str = "0.0.0.0"
    port: int = 8001


settings = Settings()
