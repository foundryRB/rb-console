"""Instantiation domain value."""
from __future__ import annotations

from enum import Enum


class Instantiation(str, Enum):
    """Which way an app is held by the foundry, DERIVED and never declared.

    The whole point is that it comes from what exists rather than from a claim: an app that
    runs on a foundry has an entry environment, and an app whose home is another
    organization's repository declares a `repository` target to reach it. Those two facts,
    read from the app's own repo, are the entire derivation - so nothing can call itself a
    tier it is not, and nothing has to be kept in sync.

    COMPLETE runs here and goes nowhere else. HYBRID runs here and has a door back to a home
    we do not own: proven live here, promoted there. MANAGED has no entry environment at all,
    so nothing can prove a release live and its bar is proven-in-CI-and-merged - which is why
    promotion never reaches it, and why that is the model working rather than a hole in it.
    """

    COMPLETE = "complete"
    HYBRID = "hybrid"
    MANAGED = "managed"
