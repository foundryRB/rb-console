"""Validate the request's maintenance ceremony mode (INT-FC-R64).

Gated is the default. The selected mode reaches the worker unchanged. One-shot
merge requires a current delegated grant, recorded PASS, and fresh green checks;
GitHub applies the repository's branch protection and required checks.
"""

from __future__ import annotations

from collections.abc import Iterable

from orchestrator.domain.maintenance import identity_set
from orchestrator.domain.model.maintenance_mode import MaintenanceMode


def parse_mode(raw: str | None) -> MaintenanceMode:
    """The request's mode, validated to the three known values; gated when unstated."""
    if raw is None or not str(raw).strip():
        return MaintenanceMode.GATED
    try:
        return MaintenanceMode(str(raw).strip())
    except ValueError as exc:
        known = ", ".join(m.value for m in MaintenanceMode)
        raise ValueError(f"unknown maintenance mode {raw!r}; one of: {known}") from exc


def is_contributor(pr_author: str, git_user: str | Iterable[str]) -> bool:
    """Whether a PR was authored by someone other than one of the console's own identities -
    'the console did not write this one'. INFORMATIONAL: it drives a badge and the merge
    button's label so the operator can see whose change they are landing. It gates nothing.
    Who may merge what is the repo's rule, and whose review counts is the playbook's
    verdict rule (INT-FC-R66), neither of which is answered by which machine accounts the console holds
    tokens for."""
    ours = identity_set(git_user)
    return not ours or (pr_author or "").strip().lower() not in ours
