"""Instantiation over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.promotion import parse_contract
from orchestrator.domain.model.instantiation import Instantiation as DomainInstantiation
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.promotion import derive_instantiation


class Instantiation:
    def __init__(self, *, psource: PromotionSource | None) -> None:
        self.psource = psource

    def execute(self, repo: str) -> DomainInstantiation:
        """Which way the foundry holds this app - derived, never declared (issue #130).

        Two facts decide it and both are read from the app's OWN repository: whether it is
        onboarded anywhere (an entry environment exists, so a release can be proven live) and
        whether its contract declares a door back to a home we do not own. Deriving beats
        storing because a stored tier is a claim that can go stale the moment an app is
        onboarded or a target declared, and every bar downstream - what done MEANS for this
        app - hangs off it.

        A console that cannot read the app's repo answers COMPLETE, the tier that grants the
        least: no door back and no foreign home, so nothing reaches outside our org on the
        strength of a read that failed.
        """
        if self.psource is None:
            return DomainInstantiation.COMPLETE
        declared, _ = parse_contract(self.psource.contract_text(repo))
        return derive_instantiation(
            has_entry_environment=bool(self.psource.deploy_installs(repo)),
            has_repository_target=any(
                t.kind is TargetKind.REPOSITORY for t in declared
            ),
        )
