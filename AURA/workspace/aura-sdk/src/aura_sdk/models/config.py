"""Configuration models — environment-based settings."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    # Service identity
    SERVICE_NAME: str = "aura-core"
    VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    # Database
    SQLITE_PATH: str = "./data/aura.db"

    # LLM Gateway
    LLM_GATEWAY_URL: str = "http://llm-gateway:8000"
    OPENAI_API_KEY: str = ""
    TOKEN_BUDGET_DAILY: int = 1_000_000
    DEFAULT_MODEL: str = "gpt-4o-2024-08-06"

    # WebSocket Server
    WS_SERVER_URL: str = "http://ws-server:8000"

    # Auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRY_HOURS: int = 24
    ADMIN_EMAIL: str = "admin@aura.local"
    ADMIN_PASSWORD: str = "admin123"

    # Agent runtime
    MAX_CONCURRENT_AGENTS: int = 50
    AGENT_TIMEOUT_SECONDS: int = 300
    RULES_PATH: str = "./rules"
    PLUGINS_PATH: str = "./plugins"

    # Simulation
    QEMU_ENABLED: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
