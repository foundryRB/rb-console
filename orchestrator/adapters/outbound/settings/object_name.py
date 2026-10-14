"""ConfigStore: the Console's runtime settings. Each setting is a named entry with
public fields (a ConfigMap) and an optional secret (a Secret), editable at runtime and
persisted, so auth or endpoints can change without a redeploy. The settings the worker
path reads:

  driver       - the home co-pilot's driver: base_url, model, and its api_key
  gitid-<name> - one machine-user git identity: name, email, login, and its token
  git-roles    - which identity each catalog agent and the console role act as
  mcp-<door>   - one owner MCP door's access: user, and its password

Either backend returns a setting's public fields plus ``configured``; the secret value
is never returned, only whether it is set.
"""
from __future__ import annotations

import re


def _rfc1123(name: str) -> str:
    """A Kubernetes object name (RFC 1123): lowercase, only [a-z0-9-], start/end alphanumeric.

    A setting name derives from a repo's delivery slug, whose case is PRESERVED so it matches
    each studio's project key (``domain.delivery_slug``); the k8s object stored under it must
    still be a valid name, so a camelCase repo (``SolveOS`` -> ``fc-target-solveos``) does not
    make ``kubectl apply`` reject the write. The credential store already lowercases its slug
    the same way, so both stores agree on the object for a given target. Idempotent and
    read/write symmetric: the same setting name always maps to the same object name.
    """
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
