"""Promotion shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.services.settings.pair_refs import helper_pair_refs
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.services.maintenance_launch import PairHome


def helper_pair_home(
    target: PromotionTarget | None, *, cap_pair_credential_held: PairCredentialHeldPort
) -> PairHome | None:
    """A Managed app's home as the compiler needs it: their repository, their base
    branch, and the refs for the credential they granted us.

    None when there is no home, and None when the credential is not held - a worker sent
    at someone else's repository without their grant cannot clone it, so compiling that
    run would spend a pod to discover what the console already knows. The caller refuses
    loudly rather than compiling a doomed act."""
    if target is None:
        return None
    refs = partial(helper_pair_refs, cap_pair_credential_held=cap_pair_credential_held)(
        target.credential
    )
    if refs is None:
        return None
    return PairHome(repo=target.repo, branch=target.branch, credential=refs)
