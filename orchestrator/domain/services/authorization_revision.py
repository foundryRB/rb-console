"""Deterministic revision of an installation's server-owned authorization policy."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable


def authorization_revision(
    admission: str, issuer: str, organization: str, repositories: Iterable[str],
    actions: Iterable[str], local_operator: str = "", admin_group: str = "",
) -> str:
    policy = [
        admission, issuer, organization, sorted(repositories), sorted(actions), local_operator,
        admin_group,
    ]
    return hashlib.sha256(json.dumps(policy).encode()).hexdigest()
