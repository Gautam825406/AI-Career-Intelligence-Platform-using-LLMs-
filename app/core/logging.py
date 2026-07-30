"""Structured logging setup.

Logs are JSON lines so they can be piped into any log aggregator. Nothing
sensitive (API keys, auth headers, full syllabus text) is ever passed to
these loggers — callers are responsible for redacting before logging, and
the helper functions below make the safe path the easy path.
"""

import json
import logging
import sys
import time
from typing import Any, Optional


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)


logger = logging.getLogger("syllabus_career_mapper")


def log_request_event(
    request_id: str,
    endpoint: str,
    status_code: int,
    total_time_ms: float,
    openai_time_ms: Optional[float] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    error_code: Optional[str] = None,
) -> None:
    """Emit one structured log line per request. Never pass syllabus text or
    secrets into `extra_fields` — this function only accepts safe, structured
    metadata by design."""

    payload: dict[str, Any] = {
        "ts": time.time(),
        "request_id": request_id,
        "endpoint": endpoint,
        "status_code": status_code,
        "total_time_ms": round(total_time_ms, 2),
    }
    if openai_time_ms is not None:
        payload["openai_time_ms"] = round(openai_time_ms, 2)
    if input_tokens is not None:
        payload["input_tokens"] = input_tokens
    if output_tokens is not None:
        payload["output_tokens"] = output_tokens
    if error_code is not None:
        payload["error_code"] = error_code

    logger.info(json.dumps(payload))
