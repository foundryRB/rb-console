"""Is the vendored pin still the playbook's current file?

Fetches every file the manifest pins - the delivery-record helpers beside this one, and the
inbox sweep and its fixture corpus under ``orchestrator/vendor/`` - from the playbook at a
ref (default ``main``) and byte-compares them with the vendored copies.

A pinned ``fixtures/`` folder is also LISTED upstream, because the refresh script mirrors it
whole: a case the playbook adds there, or drops, is drift that no comparison of the pinned
files can see. Every read is made at the one commit the ref resolves to, so a listing and
the files it names describe the same tree.

The gap it reports (issue #33): the pin can go stale in silence. The playbook's helper
gains a fix, the vendored copy keeps the old one, and every delivery pod runs the old
helper - which is how issue #2's bug would have shipped twice, since the pin predated a
``reach_gate.py`` fix that preserves run-scoped fields (``onboarding_pr:``) across a
rebuild.

**Operator-run, on the caller's own credential. Never CI.** This is the read-only twin of
``update-vendored-helpers.sh`` beside it, which already reaches the playbook the same way:
a person or a maintenance session that legitimately holds access to both repos asks the
question and decides. Wiring it into CI is the mistake this comment exists to prevent
(issue #34, reverted): it would make foundry-console's pipeline depend on another repo and
need a cross-repo secret, which is the exact coupling ``devops/vendor/`` exists to remove -
the pins are here so the build is hermetic. A pin bump is a deliberate act, not a
pipeline's business. ``tests/test_vendor_pin.py`` asserts no workflow reaches the playbook.

Stdlib only, and it talks to the REST API directly rather than shelling out to ``gh``, so
it runs from any Python without extra tooling.

    GH_TOKEN=$(gh auth token) python3 devops/vendor/check_pin_drift.py [ref]

Exit codes: 0 in sync; 1 drifted (with the refresh command); 2 could not ask upstream.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_API = "https://api.github.com"
_HERE = Path(__file__).resolve().parent
#: The folder a source pins whole: update-vendored-helpers.sh vendors every file the
#: playbook holds there, so what it holds is part of the pin.
_DISCOVERED = "fixtures/"

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def _token() -> str:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _get(path: str, token: str) -> Any:
    request = urllib.request.Request(
        f"{_API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "foundry-console-vendor-pin",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _held(repo: str, skill: str, folder: str, sha: str, token: str) -> set[str]:
    """What a skill's folder holds at a commit, named as the manifest names its files
    (``fixtures/<name>``; a subfolder keeps its trailing slash). A folder the commit lacks
    holds nothing: the commit was just read on the same credential, so its 404 is an
    answer, not a refusal."""
    try:
        listing = _get(f"/repos/{repo}/contents/{skill}/{folder.rstrip('/')}?ref={sha}", token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return set()
        raise
    return {folder + entry["name"] + ("/" if entry["type"] == "dir" else "") for entry in listing}


def main() -> int:
    ref = sys.argv[1] if len(sys.argv) > 1 else "main"
    manifest_path = _HERE / "PINNED.json"
    if not manifest_path.is_file():
        print(f"check-pin-drift: {manifest_path} is missing - the pin has no recorded home", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repo, pinned = manifest["repo"], manifest["ref"]
    root = _HERE.parents[1]

    token = _token()
    if not token:
        # No credential is an UNANSWERED question, never a pass: the playbook is private,
        # so an anonymous read cannot distinguish "in sync" from "cannot see it".
        print(
            "check-pin-drift: no GH_TOKEN/GITHUB_TOKEN in the environment; the playbook "
            "repo is private and cannot be read anonymously",
            file=sys.stderr,
        )
        return 2

    try:
        upstream = _get(f"/repos/{repo}/commits/{ref}", token)["sha"]
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError) as exc:
        print(
            f"check-pin-drift: cannot read {repo} at {ref} - the token needs contents:read "
            f"on the playbook repo ({exc})",
            file=sys.stderr,
        )
        return 2

    drifted: list[str] = []
    for path, source in sorted(manifest["sources"].items()):
        into = root / source["into"]
        pinned_names = set(source["files"])
        # Upstream's side of a pinned folder: what the playbook holds there now, which is
        # what the refresh script would vendor. None for a source that pins no folder. A
        # subfolder the pin names is listed as a folder of its own, not reported as drift.
        held = None
        folders = {name.rsplit("/", 1)[0] + "/" for name in pinned_names if name.startswith(_DISCOVERED)}
        if folders:
            try:
                held = set().union(*(_held(repo, path, folder, upstream, token) for folder in folders)) - folders
            except (urllib.error.HTTPError, urllib.error.URLError, KeyError, TypeError) as exc:
                print(f"check-pin-drift: cannot list {path}/{_DISCOVERED} in {repo}@{ref} ({exc})", file=sys.stderr)
                return 2
        for name in sorted(pinned_names | (held or set())):
            if name not in pinned_names:
                print(f"DRIFTED  {source['into']}/{name} is in {repo}@{ref} but not in the pin", file=sys.stderr)
                drifted.append(f"{source['into']}/{name}")
                continue
            if held is not None and name.startswith(_DISCOVERED) and name not in held:
                print(f"DRIFTED  {source['into']}/{name} is pinned but {repo}@{ref} does not hold it", file=sys.stderr)
                drifted.append(f"{source['into']}/{name}")
                continue
            try:
                blob = _get(f"/repos/{repo}/contents/{path}/{name}?ref={upstream}", token)
                current = base64.b64decode(blob["content"])
            except (urllib.error.HTTPError, urllib.error.URLError, KeyError) as exc:
                print(f"check-pin-drift: cannot read {path}/{name} from {repo}@{ref} ({exc})", file=sys.stderr)
                return 2
            if current == (into / name).read_bytes():
                print(f"ok       {source['into']}/{name} matches {repo}@{ref}")
            else:
                print(f"DRIFTED  {source['into']}/{name} differs from {repo}@{ref}", file=sys.stderr)
                drifted.append(f"{source['into']}/{name}")

    if drifted:
        print(
            f"\nThe vendored files are behind {repo}@{ref} "
            f"(pinned at {pinned}, upstream {upstream}): {', '.join(drifted)}.\n"
            f"Every pin moves together. Refresh and commit the bump:\n"
            f"  devops/vendor/update-vendored-helpers.sh {ref}",
            file=sys.stderr,
        )
        return 1

    print(f"in sync: pinned {pinned}, {ref} is {upstream}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
