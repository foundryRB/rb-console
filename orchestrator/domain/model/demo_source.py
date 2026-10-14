"""Immutable DemoSource worker input."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoSource:
    """The line a demo rehearses (REF-Demo): the source repository, its app's fleet name,
    and the fleet name this line's app takes. Read by the console - the seed off the repo's
    name and the org, the names off the fleet - and never declared by the operator."""

    repo: str
    app: str
    demo_app: str
