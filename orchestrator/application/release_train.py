"""Derive the release train from tags and unreleased Conventional Commits
(INT-FC-R59). The pipeline cuts versions mechanically from commit types
(fix = patch, feat = minor, breaking marker = major), so this preview computes
exactly what the release tooling will cut - or, with no releasable commits, no
next version at all. Pure.
"""

from __future__ import annotations

import re

from orchestrator.domain.maintenance import CHECKS_UNKNOWN
from orchestrator.domain.model.release_train import ReleaseTrain

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
# A Conventional Commit subject: type(scope)!: subject. The bang is the breaking marker.
_CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<bang>!)?:")
# The footer grammar the release tooling reads: a line starting the token, not a
# mere mention in prose (a revert quoting it must not bump major).
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def _parse_tag(tag: str) -> tuple[int, int, int] | None:
    m = _SEMVER.match((tag or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def latest_version(tags: list[str]) -> str:
    """The highest semver among the tags, in its bare ``x.y.z`` form; '' when none."""
    parsed = [p for p in (_parse_tag(t) for t in tags or []) if p]
    if not parsed:
        return ""
    return "{}.{}.{}".format(*max(parsed))


def derive_train(
    tags: list[str],
    unreleased_subjects: list[str],
    deployed: str = "",
    healthy: bool | None = None,
    checks: str = CHECKS_UNKNOWN,
) -> ReleaseTrain:
    """The train: version now, unreleased commits counted by type, and the computed
    next version. Entries are FULL commit messages: the type parses from the subject
    line, and the breaking marker is the subject's ``!`` or a ``BREAKING CHANGE``
    footer anywhere in the message (exactly what the release tooling reads); ``feat``
    minor; ``fix`` patch; anything else cuts nothing. No unreleased commits means no
    next version.
    """
    version = latest_version(tags)
    breaking = feat = fix = other = 0
    for message in unreleased_subjects or []:
        text = (message or "").strip()
        subject = text.splitlines()[0] if text else ""
        m = _CONVENTIONAL.match(subject)
        if m and (m.group("bang") or _BREAKING_FOOTER.search(text)):
            breaking += 1
        elif m and m.group("type") == "feat":
            feat += 1
        elif m and m.group("type") == "fix":
            fix += 1
        else:
            other += 1
    total = breaking + feat + fix + other

    next_version = ""
    if version and (breaking or feat or fix):
        major, minor, patch = (int(x) for x in version.split("."))
        if breaking:
            next_version = f"{major + 1}.0.0"
        elif feat:
            next_version = f"{major}.{minor + 1}.0"
        else:
            next_version = f"{major}.{minor}.{patch + 1}"

    return ReleaseTrain(
        version=version,
        unreleased_total=total,
        breaking=breaking,
        feat=feat,
        fix=fix,
        other=other,
        next_version=next_version,
        deployed=deployed,
        healthy=healthy,
        checks=checks,
    )
