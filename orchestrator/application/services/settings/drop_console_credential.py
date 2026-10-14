"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.services.settings.held_credential import HeldCredential


def helper_drop_console_credential(
    *, console_credential: HeldCredential | None
) -> None:
    """Invalidate the held console token (INT-FC-R143), so the next read re-resolves
    it. Called from every Settings write that can change which identity the console's
    acts and org reads run as - the late binding the per-call resolution was for."""
    if console_credential is not None:
        console_credential.invalidate()
