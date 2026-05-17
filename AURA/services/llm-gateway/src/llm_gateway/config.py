"""LLM Gateway configuration."""

import os
import shutil


class Config:
    """Service configuration loaded from environment."""

    LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "qgenie").strip().lower()
    LLM_MOCK_MODE: bool = os.environ.get("LLM_MOCK_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    QGENIE_API_KEY: str = os.environ.get("QGENIE_API_KEY", "")
    QGENIE_COMMAND: str = os.environ.get("QGENIE_COMMAND", "qgenie")
    QGENIE_CLI_HOME: str = os.environ.get("QGENIE_CLI_HOME", "")

    DEFAULT_MODEL: str = os.environ.get(
        "DEFAULT_MODEL",
        "azure::gpt-5.3-codex" if LLM_PROVIDER == "qgenie" else "gpt-4o-2024-08-06",
    )
    TOKEN_BUDGET_DAILY: int = int(os.environ.get("TOKEN_BUDGET_DAILY", "1000000"))
    CACHE_SIZE: int = int(os.environ.get("CACHE_SIZE", "10000"))
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    MAX_RETRIES: int = 3
    REQUEST_TIMEOUT: float = 120.0

    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration. Returns list of errors."""
        errors = []

        if cls.LLM_PROVIDER not in {"openai", "qgenie"}:
            errors.append(f"Unsupported LLM_PROVIDER: {cls.LLM_PROVIDER}")
            return errors

        # Development mode: allow gateway startup without provider credentials/binaries.
        if cls.LLM_MOCK_MODE:
            return errors

        if cls.LLM_PROVIDER == "openai":
            if not cls.OPENAI_API_KEY:
                errors.append("OPENAI_API_KEY is required for openai provider")
            if cls.OPENAI_API_KEY.startswith("sk-") and len(cls.OPENAI_API_KEY) < 20:
                errors.append("OPENAI_API_KEY looks invalid")
            return errors

        # qgenie provider checks
        if shutil.which(cls.QGENIE_COMMAND) is None:
            errors.append(f"QGenie command not found: {cls.QGENIE_COMMAND}")
        if not cls.QGENIE_API_KEY and not cls.QGENIE_CLI_HOME:
            errors.append("QGENIE_API_KEY or QGENIE_CLI_HOME is required for qgenie provider")
        return errors
