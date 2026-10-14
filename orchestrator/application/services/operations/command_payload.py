"""Safe command fingerprints and retained result representations."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256


def safe_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return safe_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        mapped = {
            str(key): safe_value(item)
            for key, item in value.items()
            if str(key)
            not in {
                "worker_credential",
                "credential",
                "api_key",
                "token",
                "secret",
                "password",
                "source",
            }
        }
        if isinstance(value.get("source"), bytes):
            mapped["source_sha256"] = sha256(value["source"]).hexdigest()
        return mapped
    if isinstance(value, (tuple, list)):
        return [safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
