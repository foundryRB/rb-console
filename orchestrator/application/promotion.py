"""Assemble one app's promotion view: parse its contract, read what each target
carries, and derive where each stands (REF-Promotion sections 2 to 6).

The contract is parsed here rather than trusted: the console reads the same file
the promote act reads, and a contract it cannot parse is reported as malformed
rather than silently skipped, because a promotion against a contract nobody
wrote is exactly what the loudness prevents.
"""

from __future__ import annotations

import re

from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.model.target_position import TargetPosition
from orchestrator.domain.promotion import attention_order, derive_position
from orchestrator.domain.services.repository_door import accepted_release, open_door_ref

__all__ = [
    "NOT_SUBJECT_MANAGED",
    "NOT_SUBJECT_UNPROVEN",
    "environment_version",
    "pair_door_shut",
    "parse_contract",
    "promotion_view",
]

# The version an environment currently carries, read off its values file: every
# released image is pinned at the same release, so the first tag found is the
# environment's version. Matches `tag: 1.2.3` and `tag: v1.2.3` at any depth.
_TAG = re.compile(r"^\s*tag:\s*['\"]?v?(\d+\.\d+\.\d+)['\"]?\s*$", re.MULTILINE)


def environment_version(values_text: str | None) -> str | None:
    """The release an environment carries, or None when its values are unreadable."""
    if values_text is None:
        return None
    match = _TAG.search(values_text)
    return match.group(1) if match else ""


def _unquote(value: str) -> str:
    """Strip ONE matching pair of surrounding quotes, never every quote present.

    ``strip("'\\"")`` eats quote characters from both ends until it runs out, so a
    value that legitimately begins and ends with a quote loses its own. A suite's
    pass rule is exactly that value: ``'"result":"passed"'`` came back as
    ``result":"passed`` and matched nothing. The desk's parser already stripped a
    single pair, so this was also a drift between two readers of one file.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse_contract(text: str | None) -> tuple[list[PromotionTarget], str]:
    """The declared targets and a malformation message ('' when clean).

    yaml is not imported for one small document: the contract's shape is a list
    of flat mappings, and reading it with the stdlib keeps the console's runtime
    dependency-free the way its other readers are. A line the shape does not
    admit is reported, never skipped.
    """
    if text is None:
        return [], ""
    targets: list[PromotionTarget] = []
    current: dict[str, str] = {}
    in_targets = False
    problem = ""

    def flush() -> None:
        nonlocal problem
        if not current:
            return
        name = current.get("name", "")
        kind_raw = current.get("kind", "")
        if not name or kind_raw not in ("environment", "repository"):
            problem = problem or f"target {name or '(unnamed)'}: missing name or kind"
            current.clear()
            return
        if any(t.name == name for t in targets):
            problem = problem or f"target {name!r} is declared twice"
            current.clear()
            return
        kind = TargetKind(kind_raw)
        if kind is TargetKind.ENVIRONMENT and not (
            current.get("install") and current.get("environment")
        ):
            problem = (
                problem
                or f"target {name!r}: an environment target names install and environment"
            )
            current.clear()
            return
        if kind is TargetKind.REPOSITORY and not (
            current.get("repo") and current.get("branch")
        ):
            problem = (
                problem or f"target {name!r}: a repository target names repo and branch"
            )
            current.clear()
            return
        default_door = "commit" if kind is TargetKind.ENVIRONMENT else "pull-request"
        default_terms = "version" if kind is TargetKind.ENVIRONMENT else "source"
        targets.append(
            PromotionTarget(
                name=name,
                kind=kind,
                door=current.get("door", default_door),
                terms=current.get("terms", default_terms),
                acceptance=current.get("acceptance", "none"),
                install=current.get("install", ""),
                environment=current.get("environment", ""),
                repo=current.get("repo", ""),
                branch=current.get("branch", ""),
                credential=current.get("credential", ""),
                probe_url=current.get("probe", ""),
                suite_url=current.get("suite", ""),
                suite_pass=current.get("suite_pass", ""),
            )
        )
        current.clear()

    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].rstrip() if not raw.strip().startswith("#") else ""
        if not line.strip():
            continue
        if re.match(r"^targets:\s*(\[\s*\])?\s*$", line):
            in_targets = True
            continue
        if not in_targets:
            continue
        if re.match(r"^\s*-\s", line):
            flush()
            line = re.sub(r"^\s*-\s*", "", line)
        key_value = re.match(r"^\s*([a-z_]+):\s*(.*)$", line)
        if not key_value:
            continue
        key, value = key_value.group(1), _unquote(key_value.group(2).strip())
        if key == "acceptance" and not value:
            current["acceptance"] = "probe"
            continue
        current[key] = value
    flush()
    return targets, problem


def pair_door_shut(target: PromotionTarget, registered) -> str:
    """Why this target's door cannot be opened, or '' when it can.

    Only a `repository` target has a door to shut: an environment target is written
    by a commit to a deploy branch we already hold, so the platform needs nothing
    granted to it. ``registered`` answers whether the platform holds the named pair
    credential; None means nothing can answer, and an unasked question is never
    reported as a no.
    """
    if target.kind is not TargetKind.REPOSITORY or registered is None:
        return ""
    if not target.credential:
        return "the contract names no credential for this pair"
    if not registered(target.credential):
        return f"the platform holds no credential named {target.credential}"
    return ""


#: Why an app with a contract still has no promotion positions to derive. Both are facts
#: about the APP, not about any target, which is why they are answered here rather than in
#: the per-target derivation: "nothing to promote" is zero positions, and a sixth target
#: state meaning that would be a rule the corpus's one-target-in, one-position-out shape
#: cannot carry.
NOT_SUBJECT_MANAGED = "managed"
NOT_SUBJECT_UNPROVEN = "nothing-proven"


def promotion_view(
    *,
    repo: str,
    proven: str,
    source,
    registered=None,
    has_entry_environment: bool = True,
    door=None,
) -> dict:
    """One app's promotion state: its targets, their positions, and the queue.

    ``source`` is the install-side repo-host reader; ``door`` is how a repository
    target's own repository is reached, selected per app from the credential its
    contract names (#167) - a caller with no door reads every pair as unreadable,
    exactly as an unheld credential does. ``proven`` is the release the entry
    environment serves, which the caller derives from the app's own delivery
    facts. ``registered`` answers whether the platform holds a named pair
    credential; a caller with no credential store passes none and no target is
    reported shut. An app with no contract is not a promotion subject and says so.

    Two more apps are not subjects, and both say so rather than deriving rows. An app
    with no entry environment is MANAGED: promotion moves what an entry environment
    proved, so there is nothing for it to move, and its declared repository target is
    its home - the address its maintenance and delivery lines land through, not a
    door promotion drives. And an app that has proven no release yet has nothing to
    promote, whatever it declares. Left to the per-target derivation, both came out
    PENDING (an empty proven compares unequal to anything), which put a Promote act on
    a row where no promotion is possible.

    A pair whose credential is not held is not read at all - not with the console's
    own token, which reaches our org and was never granted to theirs. Reading their
    repository on our credential is what let a target with no usable credential
    render exactly like one with a working credential, so the pane showed a row as
    current over a door that could never be performed.
    """
    text = source.contract_text(repo)
    targets, problem = parse_contract(text)
    if text is None:
        return {
            "declared": False,
            "problem": "",
            "proven": proven,
            "positions": [],
            "queue": [],
            "subject": "",
        }
    if not has_entry_environment:
        return {
            "declared": True,
            "problem": problem,
            "proven": proven,
            "positions": [],
            "queue": [],
            "subject": NOT_SUBJECT_MANAGED,
        }
    if not proven and targets:
        return {
            "declared": True,
            "problem": problem,
            "proven": proven,
            "positions": [],
            "queue": [],
            "subject": NOT_SUBJECT_UNPROVEN,
        }
    positions: list[TargetPosition] = []
    for target in targets:
        accepted: str | None
        door_ref = ""
        answers: bool | None = None
        shut = pair_door_shut(target, registered)
        if shut:
            # Nothing is asked of a pair we hold no credential for: every read
            # would fail for the one cause the row already states.
            positions.append(
                derive_position(
                    target=target, proven=proven, accepted=None, door_shut=shut
                )
            )
            continue
        if target.kind is TargetKind.ENVIRONMENT:
            accepted = environment_version(
                source.environment_values(repo, target.install, target.environment)
            )
        else:
            # A pair carries no version file of ours to read: what it accepted is
            # the release its newest merged door named, and an open door outranks
            # that comparison anyway. Both reads go through the DOOR, on the pair's
            # own credential, and what a `promote/` branch means is derived here
            # rather than asked of the host - so a second door inherits the rule.
            door_ref = (
                open_door_ref(
                    door.open_pull_requests(
                        target.repo, target.branch, target.credential
                    )
                )
                if door is not None
                else ""
            )
            accepted = (
                accepted_release(
                    door.closed_pull_requests(
                        target.repo, target.branch, target.credential
                    )
                )
                if door is not None
                else None
            )
        if target.acceptance == "probe" and target.probe_url:
            answers = source.probe(target.probe_url)
        elif target.acceptance == "suite" and target.suite_url:
            answers = source.read_suite(target.suite_url, target.suite_pass)
        positions.append(
            derive_position(
                target=target,
                proven=proven,
                accepted=accepted,
                door_open=door_ref,
                acceptance_answers=answers,
            )
        )
    return {
        "declared": True,
        "problem": problem,
        "proven": proven,
        "positions": positions,
        "queue": attention_order(positions),
        "subject": "",
    }
