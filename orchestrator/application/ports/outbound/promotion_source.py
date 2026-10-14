"""Authoritative install-side promotion observations and contract writes."""

from __future__ import annotations

from typing import Protocol


class PromotionSource(Protocol):
    def repository_revision(self, repo: str) -> str:
        """Resolve the authoritative default branch commit."""
        ...

    def contract_text(self, repo: str, *, revision: str = "") -> str | None: ...
    def environment_values(
        self, repo: str, install: str, environment: str
    ) -> str | None: ...
    def deploy_installs(self, repo: str) -> dict[str, list[str]]: ...
    def write_contract(
        self,
        repo: str,
        text: str,
        message: str,
        author: str = "",
        *,
        expected_revision: str,
    ) -> str: ...
    def probe(self, url: str) -> bool | None: ...
    def read_suite(self, url: str, match: str = "") -> bool | None: ...
