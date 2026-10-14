"""InboxItem domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InboxItem:
    """One attention line of the fleet inbox: the repo, the signal class, what it is,
    and the one act that moves it - the same queue maintenance-inbox derives by hand."""

    repo: str
    signal: str   # 'red-ci' | 'drift' | 'pr-review' | 'unreleased' | 'issue'
    detail: str
    act: str      # the one act that moves it: 'review' | 'merge' | 'resolve' | 'investigate' | 'release'
    number: int | None = None
    ts: str = ""  # the item's own timestamp for age-sort (issue created / PR last-updated); "" when a
    #             signal carries none (drift, unreleased), which sorts those to the end of an age sort.
    hidden: bool = False  # an 'issue' signal whose ticket carries the 'foundry-hidden' label
    #             (excluded by default); the repo-topic 'foundry-hidden' mirror, at issue scope.
    # Where a ticket sits in the maintenance loop right now: '' (the other signals already ARE
    # the state), 'in-progress' (a run is working it this instant), 'open' (filed, no PR yet),
    # 'awaiting-review' (a gate), 'awaiting-merge' (passed, needs the operator's merge), or
    # 'checks-red'. Lets the Inbox show a ticket's real position without a click into the
    # Maintenance pane to find out (REF-Maintenance section 6: derived, never stored).
    stage: str = ""
