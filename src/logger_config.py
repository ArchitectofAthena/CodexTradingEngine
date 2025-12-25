"""
Production logging configuration for EVE_Q SlurperBot v2.

Implements structured logging with multiple outputs:
- Console (for development/monitoring)
- File rotation (for audit trail)
- JSON structured logs (for parsing/analysis)
- Metrics export (for monitoring dashboards)
"""

import logging
import logging.handlers
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Parameters
        ----------
        record : LogRecord
            Log record to format

        Returns
        -------
        str
            JSON-formatted log entry
        """
        log_data = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add custom fields if present
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data)


class ColoredConsoleFormatter(logging.Formatter):
    """Format console logs with colors for readability."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors.

        Parameters
        ----------
        record : LogRecord
            Log record to format

        Returns
        -------
        str
            Colored log entry
        """
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"

        # Format timestamp
        timestamp = datetime.utcfromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        record.timestamp = timestamp

        return super().format(record)


def setup_logging(config: Dict[str, Any]) -> None:
    """Setup production logging configuration.

    Parameters
    ----------
    config : dict
        Configuration with logging settings
    """
    # Get logging configuration
    log_config = config.get("logging", {})
    log_level = log_config.get("level", "INFO")
    log_dir = Path(config.get("log_dir", "logs"))
    log_dir.mkdir(exist_ok=True, parents=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # 1. Console handler (colored, human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = ColoredConsoleFormatter(
        "%(timestamp)s [%(levelname)s] %(name)s: %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. File handler (rotating, plain text)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "eve_q.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 3. JSON handler (structured, machine-readable)
    json_handler = logging.handlers.RotatingFileHandler(
        log_dir / "eve_q.json",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,
        encoding="utf-8"
    )
    json_handler.setLevel(log_level)
    json_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(json_handler)

    # 4. Error file handler (errors only)
    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / "eve_q_errors.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)

    # Silence noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("web3").setLevel(logging.WARNING)
    logging.getLogger("eth_utils").setLevel(logging.WARNING)

    logging.info("=" * 70)
    logging.info("EVE_Q SlurperBot v2 - Grace Economy Edition")
    logging.info("=" * 70)
    logging.info(f"Logging initialized - Level: {log_level}")
    logging.info(f"Log directory: {log_dir.absolute()}")
    logging.info(f"Grace-based economics: ACTIVE")
    logging.info(f"Charity allocation: 15% (immutable)")
    logging.info("=" * 70)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Parameters
    ----------
    name : str
        Logger name (typically __name__)

    Returns
    -------
    Logger
        Configured logger instance
    """
    return logging.getLogger(name)


def log_with_extra(logger: logging.Logger, level: int, message: str, **kwargs):
    """Log message with extra structured data.

    Parameters
    ----------
    logger : Logger
        Logger instance
    level : int
        Log level (logging.INFO, etc.)
    message : str
        Log message
    **kwargs
        Additional data to include in JSON logs
    """
    extra = {"extra_data": kwargs}
    logger.log(level, message, extra=extra)
