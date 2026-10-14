"""Identity shared orchestration over explicit contracts."""

from __future__ import annotations

import re


def helper_agent_slug(name: str) -> str:
    return re.sub("[^a-z0-9-]", "-", (name or "").lower()).strip("-")
