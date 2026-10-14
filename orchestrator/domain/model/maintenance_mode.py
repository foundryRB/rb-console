"""MaintenanceMode domain value."""
from __future__ import annotations

from enum import Enum


class MaintenanceMode(str, Enum):
    """The ceremony, chosen per act (REF-Maintenance section 4). GATED is the default:
    ticket, branch, PR, verdict, and the operator's merge. ONE_SHOT adds the engine's
    merge over a recorded fresh-eyes PASS, under the operator's standing authorization
    for that drive. DIRECT is a conventional commit on the default branch, no PR;
    never a repo's standing default.
    """

    GATED = "gated"
    ONE_SHOT = "one-shot"
    DIRECT = "direct"
