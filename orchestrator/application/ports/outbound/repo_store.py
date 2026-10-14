"""Application contracts for external capabilities."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.repository_identity import RepositoryIdentity
from orchestrator.domain.model.source_file import SourceFile

__all__ = ["RepoStore"]


class RepoStore(Protocol):
    def list_delivery_repos(self) -> list[str]:
        """Local workspace paths of the known delivery repos (those carrying a live
        scratch: the delivery/* ref, mounted at .delivery/ in a working checkout)."""
        ...

    def ensure(self, target: str) -> str:
        """Return a local workspace path for target, creating the repo if it does
        not exist (greenfield) or cloning it if it does (adopt). Does not create
        the scratch; that is register's job."""
        ...

    def repo_exists(self, target: str) -> bool:
        """Whether the target repo is already there, under that exact name - the
        create-vs-adopt branch ensure() takes, asked before it takes it. Optional:
        a store that does not offer it leaves the caller unable to tell the two
        apart, and callers must default to the safer of the two (see
        the repository establishment capability)."""
        ...

    def register(
        self,
        workspace: str,
        request: str = "",
        source: Sequence[SourceFile] = (),
        source_name: str = "",
    ) -> None:
        """Make the repo a delivery: mint its one orphan delivery/<line-id> scratch ref
        carrying the skeleton (records at the branch root), refuse a second while any
        delivery/* ref exists, ensure the default branch git-ignores the .delivery/
        mount point, capture the customer's verbatim request, and - for a recast - land
        the source app under _recast/ on that scratch, minting the seed/<slug> tag on
        the register commit so the line reads as a recast off the repo (REF-Delivery
        section 2) when given. Idempotent: an existing line is adopted, and an existing
        request is never overwritten."""
        ...

    def write_gate(
        self, workspace: str, record: str, date: str, *, definition: LifecycleDefinition, expected_revision: str = ""
    ) -> None:
        """Stamp a gate signature (the date) into a phase's record, releasing the next phase."""
        ...

    def reopen_gate(
        self, workspace: str, record: str, *, expected_revision: str = ""
    ) -> None:
        """Re-open a phase: un-sign its gate (its stamped date reads PENDING) and hand the
        record back to the record helper as opened-for-work, so the block reads
        `status: in-progress` with the previous attempt's evidence (`reviewed:`,
        `finished:`, `attests:`) cleared. Reverses write_gate. Downstream records are
        untouched, so they survive for review."""
        ...

    def write_config(
        self,
        workspace: str,
        config: dict,
        *,
        lifecycle: LifecycleDefinition | None = None,
    ) -> None:
        """Persist the delivery-level config (mode) to the scratch's config.json, on the
        line's ref, with the line's captured lifecycle definition when one is given. This
        travels with the delivery (GitOps), so a worker or tool reads the same truth."""
        ...

    def append_journal(self, workspace: str, entry: str) -> None:
        """Append an entry to the scratch journal (journal.md on the line's ref,
        creating it if absent): the line's running trail. A gate re-drive records the
        operator's feedback here BEFORE the run is submitted, so the review conversation
        survives in the scratch whatever the re-driven worker rewrites."""
        ...

    def close_line(self, workspace: str, *, expected_revision: str = "") -> None:
        """Close the delivery line: mint the annotated delivered/<slug>/P<n> tag on the
        scratch ref's tip and push it, THEN delete the delivery/<line-id> ref - tag
        before delete, mandatorily, since the tag is what keeps the line's record trail
        reachable. The explicit end of a line - after Learn, or in place of it.
        Idempotent: a repo with no delivery/* ref already reads closed."""
        ...

    def repository_identity(self, repository: str) -> RepositoryIdentity | None:
        """Read the authoritative repository host ID; only confirmed absence is None."""
        ...
