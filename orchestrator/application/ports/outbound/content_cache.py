"""Bounded cache for explicitly requested immutable content."""

from typing import Protocol


class ContentCache(Protocol):
    def get(self, key: tuple[str, str, str]) -> object | None: ...
    def put(self, key: tuple[str, str, str], value: object) -> None: ...
