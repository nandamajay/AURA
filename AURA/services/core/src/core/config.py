"""Core service configuration."""

import os


class Config:
    """Service configuration."""

    # Service identity
    SERVICE_NAME: str = "aura-core"
    VERSION: str = "0.1.0"
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # Database
    SQLITE_PATH: str = os.environ.get("SQLITE_PATH", "./data/aura.db")

    # External services
    LLM_GATEWAY_URL: str = os.environ.get("LLM_GATEWAY_URL", "http://llm-gateway:8000")
    WS_SERVER_URL: str = os.environ.get("WS_SERVER_URL", "http://ws-server:8000")

    # Auth
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "change-me")
    JWT_EXPIRY_HOURS: int = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))
    ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "admin@aura.local")
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Agent runtime
    MAX_CONCURRENT_AGENTS: int = int(os.environ.get("MAX_CONCURRENT_AGENTS", "50"))
    AGENT_TIMEOUT_SECONDS: int = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "300"))
    RULES_PATH: str = os.environ.get("RULES_PATH", "/rules")
    PLUGINS_PATH: str = os.environ.get("PLUGINS_PATH", "/plugins")

    # Simulation
    QEMU_ENABLED: bool = os.environ.get("QEMU_ENABLED", "false").lower() == "true"

    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration. Returns list of errors."""
        errors = []
        if not cls.JWT_SECRET or len(cls.JWT_SECRET) < 16:
            errors.append("JWT_SECRET must be at least 16 characters")
        if cls.JWT_SECRET == "change-me":
            errors.append("JWT_SECRET is using default value")
        return errors
