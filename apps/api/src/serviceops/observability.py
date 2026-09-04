import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "cvv",
    "password",
    "payment_details",
    "secret",
    "session_token",
    "set_cookie",
    "user_id",
}

request_logger = logging.getLogger("serviceops.request")
request_logger.setLevel(logging.INFO)
if not request_logger.handlers:
    request_handler = logging.StreamHandler()
    request_handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(request_handler)


def normalize_trace_id(value: str | None) -> str:
    if value and TRACE_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid.uuid4())


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return (
        normalized in SENSITIVE_KEYS
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
    )


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    return value


def log_request_event(level: int, event: str, **fields: Any) -> None:
    payload = redact({"event": event, **fields})
    request_logger.log(
        level,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
    )
