"""Identity shared orchestration over explicit contracts."""

from __future__ import annotations

import re


def helper_norm_slug(slug: str) -> str:
    """A delivery identity robust to separator/case drift: lowercased, alphanumerics only.
    'shattered-catacombs' and 'shatteredcatacombs' collapse to the same key, so a re-drive
    supersedes a run left by a differently-punctuated address of the same delivery."""
    return re.sub("[^a-z0-9]", "", slug.lower())
