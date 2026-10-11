import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for production and diagnostic logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    logger = logging.getLogger()
    logger.setLevel(level.upper())

    # Remove existing handlers to avoid duplicates
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        standard_format = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
        handler.setFormatter(logging.Formatter(standard_format, datefmt="%Y-%m-%d %H:%M:%S"))

    logger.addHandler(handler)
