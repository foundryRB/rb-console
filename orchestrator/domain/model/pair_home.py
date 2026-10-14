"""Immutable PairHome worker input."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.pair_credential import PairCredential


@dataclass(frozen=True)
class PairHome:
    """An app's HOME when the foundry does not hold it: the repository its code actually lives
    in, the branch its work lands on, and the credential that pair granted us to reach it.

    A Managed app's line runs over two repositories at once and they answer different
    questions. The foundry-side repo is OURS - it carries the ticket, and it is where the
    console reads and writes anything of the line's own. The home is THEIRS: the code is
    cloned from it and the pull request is opened on it. Nothing about that is a fallback or
    a redirect; they are two coordinates, and conflating them is what would either work the
    wrong tree or file the fix where nobody is looking.
    """

    repo: str            # owner/name on the pair's host
    branch: str          # the base branch their work lands on
    credential: PairCredential
