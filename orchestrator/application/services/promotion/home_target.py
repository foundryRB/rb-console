"""Promotion shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.promotion import parse_contract
from orchestrator.domain.model.instantiation import Instantiation
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind


def helper_home_target(
    repo: str, *, psource: PromotionSource | None, cap_instantiation: InstantiationPort
) -> PromotionTarget | None:
    """The repository target that is this app's HOME, for an app the foundry does not
    hold: the door its lines land their work through.

    Only a Managed app has one. A Hybrid app declares the same shape, but its work is
    built and proven HERE and promoted there afterwards - so its maintenance runs on our
    own repository, and reaching for the home would send an ordinary ticket's fix into
    someone else's review queue. The tier is what separates them, which is exactly why it
    is derived rather than declared.

    The first declared repository target when there are several: a Managed app has one
    home by construction (it is where its code lives), and a contract carrying two says
    something the model has no answer for - so this picks the one the contract names
    first rather than inventing a rule nobody wrote.
    """
    if psource is None:
        return None
    declared, _ = parse_contract(psource.contract_text(repo))
    target = next((t for t in declared if t.kind is TargetKind.REPOSITORY), None)
    if target is None:
        return None
    return target if cap_instantiation.execute(repo) is Instantiation.MANAGED else None
