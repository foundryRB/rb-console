from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from orchestrator.domain.exceptions.permission_denied import PermissionDenied


@dataclass(frozen=True)
class CommandContext:
    """Authority supplied by an authenticated inbound boundary."""

    principal_id: str
    initiator_kind: Literal["operator", "scheduler", "local", "machine"]
    grant_id: str
    allowed_actions: frozenset[str]
    repositories: frozenset[str]
    authorization_revision: str
    installation_id: str
    expires_at: datetime | None = None
    #: The teams the caller belongs to, resolved from its identity-provider groups.
    teams: frozenset[str] = frozenset()
    #: An admin sees every repository and holds the team settings; a team member sees
    #: only the repositories in its scope.
    admin: bool = False
    #: How the caller is shown to people: the signed-in email, else the principal.
    principal_label: str = ""
    #: Where a team member may open a line on a new repository: the installation's scope.
    claimable: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_actions", frozenset(self.allowed_actions))
        object.__setattr__(self, "repositories", frozenset(self.repositories))
        object.__setattr__(self, "teams", frozenset(self.teams))
        object.__setattr__(self, "claimable", frozenset(self.claimable))

    def authorize(
        self, action: str, repository: str = "", *,
        current_authorization_revision: str | None = None,
        now: datetime | None = None,
    ) -> None:
        valid = (
            self.principal_id and self.grant_id and self.authorization_revision
            and self.installation_id and self.initiator_kind in {"operator", "scheduler", "local", "machine"}
            and action in self.allowed_actions
        )
        if repository:
            repository = self.repository_id(repository)
            valid = valid and self.in_scope(repository)
        if current_authorization_revision is not None:
            valid = valid and self.authorization_revision == current_authorization_revision
        if self.expires_at is not None:
            valid = valid and self.expires_at.tzinfo is not None
            if self.expires_at.tzinfo is not None:
                valid = valid and (now or datetime.now(UTC)) < self.expires_at
        if self.initiator_kind == "machine":
            valid = valid and bool(repository)
        if self.initiator_kind == "scheduler":
            valid = valid and bool(repository) and self.expires_at is not None
            valid = valid and action in {"maintenance.reconcile", "maintenance.drive", "maintenance.merge", "runs.archive"}
        if not valid:
            raise PermissionDenied("No current grant permits this operation.")

    def sees(self, repository: str | None) -> bool:
        """Whether the caller may read a repository's projects, lines, runs and logs: an
        admin reads every one, anyone else only what its scope names. A read naming no
        repository, or one that is not a repository identity, is an admin's alone."""
        if self.admin:
            return True
        if not repository:
            return False
        try:
            return self.in_scope(self.repository_id(repository))
        except PermissionDenied:
            return False

    def in_scope(self, repository: str) -> bool:
        """Whether a normalized repository id is in scope: named exactly, or under an
        `owner/prefix*` entry (`owner/*` is every repository of the owner)."""
        return _covered(repository, self.repositories)

    def may_claim(self, repository: str) -> bool:
        """Whether a normalized repository id lies in the installation's scope, where a
        team member may open a line on a repository no team holds yet."""
        return _covered(repository, self.claimable)

    def repository_id(self, repository: str) -> str:
        if "://" in repository:
            parsed = urlsplit(repository)
            if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
                raise PermissionDenied("The repository is outside the installation scope.")
            repository = parsed.path.strip("/")
        repository = repository.removesuffix(".git")
        if "/" not in repository:
            repository = self.installation_id + "/" + repository
        if len(repository.split("/")) != 2 or any(part in {"", ".", ".."} for part in repository.split("/")):
            raise PermissionDenied("The repository identity is invalid.")
        return repository.lower()


def _covered(repository: str, entries: frozenset[str]) -> bool:
    return any(
        repository == entry
        or (entry.endswith("*") and "/" in entry and repository.startswith(entry[:-1]))
        for entry in entries
    )
