"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.git_credential_check import (
    GitCredentialCheck,
)


def helper_reject_invalid_git_token(
    token: str, login: str, *, gitcheck: GitCredentialCheck | None
) -> None:
    """The save-time preflight for a git identity's PAT (INT-FC-R142), the git twin of
    _reject_invalid_credential above. Fail-closed only on an explicit refusal: a 401/403,
    or a PAT belonging to an account other than the declared login. No check wired, or a
    transport failure, is not evidence the token is wrong (fail-open) - it is seated and
    the first real clone will tell, exactly as before this preflight existed."""
    if gitcheck is None:
        return
    verdict, detail = gitcheck.validate_identity(token, login)
    if verdict is False:
        raise ValueError(f"git token rejected: {detail}")
