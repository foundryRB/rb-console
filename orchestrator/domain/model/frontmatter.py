"""Delivery record frontmatter values."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Frontmatter:
    status: str = ""
    phase: str = ""
    skill: str = ""
    gate: str = ""
    signed_on: str = ""
    signed: bool = False   # a real date stamps True; 'pending' or absent stays False
    reviewed: bool = False  # a real date in `reviewed:` (the recorded fresh-eyes review)
    run: str = ""
    attempt: int = 0
    mode: str = ""
    credential_ref: str = ""
    # The journal's own field: the ISO date reconcile-delivery stamped when Learn
    # executed ("" until then, or when the value is not a date).
    learned: str = ""
    # Why a one-shot stamp left this record's gate open (#181): the gate stamper's own
    # refusal line, set only when the stamp refused over a passing review ("" otherwise).
    stamp_refused: str = ""
