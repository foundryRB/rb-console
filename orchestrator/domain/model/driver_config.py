"""DriverConfig domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriverConfig:
    base_url: str = ""
    model: str = ""
    configured: bool = False  # an api_key is set in the store; the value is never exposed
    agent: str = ""  # the saved agent backing the driver, "" when the config was set directly
