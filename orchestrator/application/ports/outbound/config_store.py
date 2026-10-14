"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.repository_identity import RepositoryIdentity

__all__ = ["ConfigStore"]


class ConfigStore(Protocol):
    def get_setting(self, name: str) -> dict:
        """Read a named runtime setting's public fields plus 'configured'; never the secret."""
        ...

    def put_setting(self, name: str, fields: dict, secret: str | None) -> dict:
        """Persist a named setting's fields and optional secret. An empty secret keeps the stored one."""
        ...

    def get_secret(self, name: str) -> str:
        """Read a setting's secret value (server-side only; never returned by a door)."""
        ...

    def list_settings(self, prefix: str) -> list[dict]:
        """Every setting whose name starts with prefix, with public fields + configured flag."""
        ...

    def delete_setting(self, name: str) -> None:
        """Remove a named setting (its ConfigMap + Secret)."""
        ...

    def repository_identity(self, slug: str) -> RepositoryIdentity | None:
        """Read the durable binding for target settings; unavailable reads must fail."""
        ...

    def bind_repository_identity(self, slug: str, identity: RepositoryIdentity) -> None:
        """Persist the immutable repository identity after successful reconciliation."""
        ...
