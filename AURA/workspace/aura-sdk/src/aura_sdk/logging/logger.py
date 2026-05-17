"""JSON logger factory using structlog.

Fallback to standard library logging if structlog is not installed.
"""

import json
import logging
import sys
from typing import Any

# Try structlog, fall back to stdlib
try:
    import structlog

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


def _json_formatter(record: logging.LogRecord) -> str:
    """Format log record as JSON."""
    log_dict = {
        "timestamp": record.created,
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
        "module": record.module,
        "function": record.funcName,
        "line": record.lineno,
    }
    # Add extra fields from record
    if hasattr(record, "event_type"):
        log_dict["event_type"] = record.event_type
    if hasattr(record, "trace_id"):
        log_dict["trace_id"] = record.trace_id
    if record.exc_info:
        log_dict["exception"] = record.exc_text

    return json.dumps(log_dict, default=str)


class _JSONHandler(logging.StreamHandler):
    """Emit log records as JSON lines to stdout."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = _json_formatter(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure logging for AURA services.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON. If False, output human-readable.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root.handlers = []

    if json_output:
        handler = _JSONHandler(sys.stdout)
    else:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)

    root.addHandler(handler)

    # Configure structlog if available
    if STRUCTLOG_AVAILABLE:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> Any:
    """Get a logger instance.

    Returns structlog BoundLogger if available, else stdlib Logger.
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    return logging.getLogger(name)
