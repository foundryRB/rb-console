"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.repository_file import RepositoryFile
from orchestrator.domain.model.repository_inventory_entry import (
    RepositoryInventoryEntry,
)
from orchestrator.domain.model.repository_tree_entry import RepositoryTreeEntry

__all__ = ["DeliverySource"]


class DeliverySource(Protocol):
    def scan(self) -> list[DeliveryState]:
        """Discover every delivery and derive its state (e.g. scan the org for repos
        carrying a live delivery/* scratch ref; more than one ref surfaces as an
        anomaly state, never a silent pick). Called out of band to refresh the index,
        never on a read request.

        Raises SourceUnavailable when the scan could not be MADE; an empty list means
        the scan ran and found no delivery (INT-FC-R144)."""
        ...

    def list_org_repos(self) -> list[RepositoryInventoryEntry]:
        """Every repo in the org (full_name, name, updated_at, topics) - the list the
        Fleet view joins on and the inbox sweeps. Raises SourceUnavailable when the org
        could not be read; an empty list means an org with no repos (INT-FC-R144)."""
        ...

    def state_of(self, repo: str) -> DeliveryState:
        """Resolve one repo's state directly (e.g. right after it is created, before the
        next background scan reaches it)."""
        ...

    def read_config(self, repo: str, *, revision: str = "") -> dict:
        """The delivery-level config (mode) from the scratch's config.json on the
        line's ref, or {} when absent. Read live, like state_of."""
        ...

    def present_records(self, repo: str) -> list[str]:
        """Which phase record files exist in the scratch (the line's ref; locally, the
        .delivery/ mount), independent of gate state. The overview needs this so a
        re-opened gate shows downstream records as present-but-stale rather than gone
        (the resolver truncates at the first gap)."""
        ...

    def tree(
        self, repo: str, *, revision: str = "", scratch_revision: str = ""
    ) -> list[RepositoryTreeEntry]:
        """The repo's file tree (path/type/size) in the working-checkout view - the
        default branch with the scratch surfaced under .delivery/ - for the worktree
        IDE."""
        ...

    def file(self, repo: str, path: str, *, revision: str = "") -> RepositoryFile:
        """One file's text (path/content/size) in the same working-checkout view: a
        .delivery/ path resolves against the line's ref at branch root, anything else
        against the default branch. For the worktree IDE and chat references."""
        ...

    def content_revision(self, repo: str, path: str = "") -> str:
        """Resolve the requested content view to immutable source commit identity."""
        ...
