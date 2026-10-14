"""Compile one promotion into an Argo Workflow: the console drives the act it names
(issue #131).

Pure, like the delivery and maintenance compilers, and built on the SAME worker template, so
every launch guard holds here by construction. The worker reads the pinned `promote` skill from
the playbook copy in its image; the console carries no copy of the act.

Why a WORKER and not the console itself. A `terms: source` door pushes a tree - a real git
push of the release's source to another organization's repository - which the console's own
repo-host reads cannot do and should not learn to. The worker path already clones into an
ephemeral workspace and takes its secrets as env-from-Secret-ref, which is exactly the shape a
pair credential needs: only the ref travels, and the value is read inside the pod. The desk
performs no door either (INT-FOUNDRY-TERMINAL-055), so this is the ONE place a door is
performed, and it is the same skill a hand would run.

The refusals live here rather than in the worker. A promotion that cannot be performed must be
refused where the operator is, at compile, not discovered by a pod six seconds in - and one of
them is doctrine rather than mechanics: an app with no entry environment is Managed, its
changes cross back through the delivery or maintenance line, and promotion never reaches it.
"""
from __future__ import annotations

from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.services.delivery_launch import (
    HEADLESS_TURN,
    pinned_skill_instruction,
)

_API = "argoproj.io/v1alpha1"

#: The one act, and the skill it runs. There is no second way to promote.
PROMOTE_SKILL = "promote"
PROMOTE_PHASE = "promotion:promote"
#: WHO performs the door: the catalog's Release Manager, the one agent that commits into
#: somewhere other than this app's default branch.
PROMOTE_AGENT = "release-manager"

_NEVER = (
    "Never relax the proven check to make a promotion possible, never inline or paste a "
    "credential, and never fall back to another token when the declared one is missing: a "
    "door that cannot be opened is a refusal, not a prompt."
)

#: interaction=auto ALWAYS in a pod - no human is reachable (INT-FC-R39), and a skill left on
#: its manual default would stop to ask and hang the worker until its deadline.
_AUTO = " Run with interaction=auto: you are headless and no human can answer you."

#: The commit-hygiene rule every compiler carries (INT-FC-R123): a promotion COMMITS (a deploy
#: branch write, or the promote branch itself), and the shared CI's hygiene gate rejects any
#: co-author or AI-attribution trailer, so a single such commit reds the branch and ships nothing.
_HYGIENE = (
    " Write commit messages with NO co-author trailer and no AI-attribution of any kind."
)

#: The landing rule every compiler carries on one headless-turn statement (INT-FC-R158): a
#: headless single-turn agent has no next turn to wake it, so work that is not landed before it
#: stops is work that died in the pod while the run still read Succeeded.
_NO_PARK = (
    f" Land the door BEFORE this run ends: {HEADLESS_TURN} - the commit, the pushed branch and "
    "(for a pair) the open pull request must actually exist when you stop, or the run has failed."
)


class PromotionRefused(ValueError):
    """A promotion the contract, the platform, or the model will not admit, phrased for the
    operator. A ValueError so the HTTP door surfaces it as a 422 like every other refusal."""


def build_promotion_prompt(repo: str, target: PromotionTarget, release: str) -> str:
    """The worker's instruction: run the playbook's own promote skill against one declared
    target. The console names the act and states the facts it already resolved; it never
    restates the act's steps, which live in the skill the worker pulls live."""
    where = (
        f"the {target.install} install's {target.environment} environment"
        if target.kind is TargetKind.ENVIRONMENT
        else f"{target.repo} (base branch {target.branch})"
    )
    door = (
        "Its door is a commit to this app's own deploy branch."
        if target.kind is TargetKind.ENVIRONMENT
        else (
            f"Its door is a pull request theirs to review. The credential the contract names "
            f"({target.credential}) is already resolved for you, for FC_PAIR_HOST: git is "
            f"configured to use it for that repository, and \"$FC_PAIR_DOOR\" carries it for the "
            f"API. It is not in your environment, by design; do not look for it, print it, or "
            f"write it anywhere. "
            # The push is authenticated by the git credential helper; the API call is not, and
            # plain gh would carry OUR token against a repository nobody granted it to us for
            # (foundry-platform#167). One door for every act on their repo, named explicitly.
            f"PUSH the promote branch with git as normal. To OPEN the pull request on "
            f"{target.repo}, and for any other API call against it, run \"$FC_PAIR_DOOR\" in "
            f"place of `gh` with the same arguments (for example: \"$FC_PAIR_DOOR\" pr create "
            f"--repo {target.repo} --base {target.branch} ...). Plain `gh` carries the "
            f"foundry's own credential, which reaches our org and was never granted to theirs."
        )
    )
    return (
        pinned_skill_instruction("promote") + f"Run promote for repo {repo}: promote release "
        f"{release} to the declared target '{target.name}', which is {where}. {door} "
        f"Follow the skill's pre-flight in full - a release that is not proven is refused, not "
        f"warned. {_NEVER}" + _AUTO + _HYGIENE + _NO_PARK
    )


def refuse_promotion(
    *,
    target: PromotionTarget | None,
    target_name: str,
    declared: list[PromotionTarget],
    release: str,
    door_shut: str = "",
    has_entry_environment: bool = True,
) -> None:
    """Raise PromotionRefused when this promotion must not be compiled at all.

    Every refusal here is one the operator can act on, stated before a pod exists. They are
    ordered by how fundamental they are: what the app IS, then whether the destination is
    real, then whether the door can be performed, then whether there is anything to carry.
    """
    # Doctrine first. Promotion moves what an entry environment PROVED, so an app with none is
    # not a promotion subject at all - it is Managed, and its pull request is its delivery or
    # maintenance line's own output at the proven-in-CI bar. This is the model working, not a
    # gap: a build that lets a promotion reach a Managed app has broken it (issue #130).
    if not has_entry_environment:
        raise PromotionRefused(
            "this app has no entry environment, so it is Managed: nothing here can prove a "
            "release live, and its changes cross back through the delivery or maintenance "
            "line rather than through a promotion"
        )
    if target is None:
        known = ", ".join(t.name for t in declared) or "(none)"
        raise PromotionRefused(
            f"this app declares no target named {target_name!r}; it declares: {known}"
        )
    if door_shut:
        raise PromotionRefused(f"the door cannot be opened: {door_shut}")
    if not (release or "").strip():
        raise PromotionRefused(
            "no release to promote: the app has published none, or none was named"
        )
