"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.credential_store import CredentialStore


def helper_has_delivery_cred(slug: str, *, credentials: CredentialStore | None) -> bool:
    return bool(credentials is not None and credentials.has_delivery(slug))
