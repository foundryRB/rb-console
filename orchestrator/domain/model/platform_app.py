"""Platform application identity and observed deployment facts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformApp:
    name: str
    repository: str
    onboarded: bool = False
    status: str | None = None
    hostname: str = ""
    revision: str = ""
    role: str | None = None
