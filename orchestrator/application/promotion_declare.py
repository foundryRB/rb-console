"""Declare a target: render the contract a hand would have written.

The console writes `devops/promotion.yaml` itself so an app can gain a target
without anyone editing YAML, and the file it writes is the file the platform
scaffolds and the promote act reads (REF-Promotion section 2). Rendering, not
patching: the contract is small, every field is explicit by rule, and a
round-trip through the parser is what proves the write is readable.
"""

from __future__ import annotations

import re

from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind

__all__ = ["ContractError", "declare_target", "render_contract"]

_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_PAIR = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

_HEADER = """\
# The app's promotion contract: where proven releases move beyond the entry
# environment. Each target carries its door (how the write is submitted),
# terms (what is written, and what deployed means) and acceptance (what
# proven-there means), written out in full; nothing is resolved by an engine
# at run time. Credentials are named here and held by the platform, never
# stored in any repository.
"""


class ContractError(ValueError):
    """A declaration the contract would not admit, phrased for the operator."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def render_contract(targets: list[PromotionTarget]) -> str:
    """The whole contract file for these targets, every field written out."""
    lines = [_HEADER.rstrip("\n"), "targets:" if targets else "targets: []"]
    for target in targets:
        lines.append(f"  - name: {target.name}")
        lines.append(f"    kind: {target.kind.value}")
        if target.kind is TargetKind.ENVIRONMENT:
            lines.append(f"    install: {target.install}")
            lines.append(f"    environment: {target.environment}")
        else:
            lines.append(f"    repo: {target.repo}")
            lines.append(f"    branch: {target.branch}")
            lines.append(f"    credential: {target.credential}")
        lines.append(f"    door: {target.door}")
        lines.append(f"    terms: {target.terms}")
        if target.acceptance == "probe" and target.probe_url:
            lines.append("    acceptance:")
            lines.append(f"      probe: {target.probe_url}")
        else:
            lines.append(f"    acceptance: {target.acceptance}")
    return "\n".join(lines) + "\n"


def declare_target(
    *,
    existing: list[PromotionTarget],
    name: str,
    kind: str,
    install: str = "",
    environment: str = "",
    repo: str = "",
    branch: str = "",
    credential: str = "",
    probe_url: str = "",
    entry_environments: dict[str, str] | None = None,
) -> list[PromotionTarget]:
    """The target list with this one added, or a ContractError naming the refusal.

    Every rule the doctrine states is enforced here rather than at the act: a
    target the contract could not admit is refused where the operator is, not
    hours later when a promotion tries to use it.
    """
    name = (name or "").strip()
    _require(
        bool(_NAME.match(name)),
        "a target's name is a lowercase label (letters, digits, hyphens)",
    )
    _require(
        not any(target.name == name for target in existing),
        f"this app already declares a target named {name!r}",
    )
    _require(
        kind in ("environment", "repository"),
        "a target is an environment or a repository",
    )

    if kind == "environment":
        install, environment = (install or "").strip(), (environment or "").strip()
        _require(
            bool(install) and bool(environment), "name the install and the environment"
        )
        entry = (entry_environments or {}).get(install, "")
        _require(
            environment != entry,
            f"{install}'s {environment} is its entry environment: it is deployed "
            "automatically, so a promotion into it would be overwritten by the next release",
        )
        _require(
            not any(
                target.kind is TargetKind.ENVIRONMENT
                and target.install == install
                and target.environment == environment
                for target in existing
            ),
            f"{install} / {environment} is already declared as a target",
        )
        target = PromotionTarget(
            name=name,
            kind=TargetKind.ENVIRONMENT,
            door="commit",
            terms="version",
            acceptance="probe" if probe_url else "none",
            install=install,
            environment=environment,
            probe_url=probe_url.strip(),
        )
    else:
        repo, branch, credential = (
            (repo or "").strip(),
            (branch or "").strip(),
            (credential or "").strip(),
        )
        _require(bool(_PAIR.match(repo)), "the pair's repository reads owner/name")
        _require(bool(branch), "name the base branch changes land on")
        _require(
            bool(credential),
            "name the credential the platform holds for this pair; the secret itself never enters the contract",
        )
        target = PromotionTarget(
            name=name,
            kind=TargetKind.REPOSITORY,
            door="pull-request",
            terms="source",
            acceptance="probe" if probe_url else "none",
            repo=repo,
            branch=branch,
            credential=credential,
            probe_url=probe_url.strip(),
        )
    return [*existing, target]
