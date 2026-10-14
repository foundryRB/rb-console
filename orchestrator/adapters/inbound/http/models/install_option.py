from __future__ import annotations

from pydantic import BaseModel


class InstallOption(BaseModel):
    install: str
    entry: str
    environments: list[str]
