"""The door's SELECTOR: which implementation performs a read, decided per app
(foundry-platform#167, ADR-044 section 6).

ADR-044 records scope as a column rather than a category, and this seam's scope is the
app: one install serves several customers at the same time, and the moment a second
customer arrives on a second host, one install needs two implementations at once. That
is not speculative - it is the Hybrid and Managed instantiations working as designed.

The chain that makes selection per-app is three links, each already owned by someone:
the app's promotion contract names a ``credential``; that credential's registration
names the ``host`` it reaches (#131, where the field has been carried since the registry
shipped); and the host names the implementation. Nothing new is declared anywhere, and
adding the second implementation is one more entry in the table this class is given.
"""

from __future__ import annotations

import logging

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest

_LOG = logging.getLogger(__name__)

#: The host assumed when a credential's registration carries none. Registrations made
#: before the field existed read as github.com, which is what they were.
DEFAULT_HOST = "github.com"


class HostSelectedDoor:
    """A ``Door`` that resolves the implementation per call, from the credential's host.

    Itself a Door, so every caller stays innocent of the fact that selection happens at
    all: the maintenance view and the promotion derivation ask for a pull request, and
    which organisation's host answers is this class's business alone."""

    def __init__(self, implementations: dict, host_provider) -> None:
        self._implementations = implementations
        # callable: credential name -> the host that credential reaches, live, so a
        # registration corrected in Settings takes effect with no redeploy.
        self._host_provider = host_provider

    def pull_request(
        self, repo: str, number: int, credential: str
    ) -> MaintenancePullRequest | None:
        door = self._for(credential)
        return door.pull_request(repo, number, credential) if door else None

    def repository_revision(self, repo: str, branch: str, credential: str) -> str:
        door = self._for(credential)
        if door is None:
            raise SourceUnavailable("The repository host has no configured door.")
        return door.repository_revision(repo, branch, credential)

    def open_pull_requests(
        self, repo: str, base: str, credential: str
    ) -> tuple[MaintenancePullRequest, ...] | None:
        door = self._for(credential)
        return door.open_pull_requests(repo, base, credential) if door else None

    def closed_pull_requests(
        self, repo: str, base: str, credential: str
    ) -> tuple[MaintenancePullRequest, ...] | None:
        door = self._for(credential)
        return door.closed_pull_requests(repo, base, credential) if door else None

    # -- selection ----------------------------------------------------------------

    def _for(self, credential: str):
        """The implementation for this credential's host, or None when this Foundry has
        none for it.

        A host with no implementation degrades exactly as an unheld credential does, and
        says so once in the log rather than raising: the surfaces already have a shape for
        "this door could not be read", and inventing a second failure mode for it would
        make an install's missing implementation look like an outage. Writing that
        implementation is the answer, and it is written the day a customer needs it."""
        host = (self._host_provider(credential) if credential else "") or DEFAULT_HOST
        door = self._implementations.get(host)
        if door is None:
            _LOG.warning(
                "no door implementation for host %s (credential %s): the read degrades",
                host,
                credential,
            )
        return door
