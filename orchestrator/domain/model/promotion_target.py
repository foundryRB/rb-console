"""PromotionTarget domain value."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.target_kind import TargetKind


@dataclass(frozen=True)
class PromotionTarget:
    """One destination as the app's contract declares it. ``door``, ``terms`` and
    ``acceptance`` are carried verbatim: the contract states them in full, and the
    console reports what it read rather than a shape it assumed."""

    name: str
    kind: TargetKind
    door: str
    terms: str
    acceptance: str
    install: str = ""
    environment: str = ""
    repo: str = ""
    branch: str = ""
    credential: str = ""
    probe_url: str = ""
    # A suite acceptance carries a coordinate and a pass rule: where the app's
    # own integrated suite publishes its verdict, and what passing looks like in
    # that answer. Never how to run one - who executes a suite is outside the
    # contract, because a destination we can write to may be on a network we
    # have no path into (REF-Promotion section 3).
    suite_url: str = ""
    suite_pass: str = ""

    @property
    def destination(self) -> str:
        """How the destination reads on a screen: install and environment, or the
        pair's repo and base branch."""
        if self.kind is TargetKind.ENVIRONMENT:
            return f"{self.install} / {self.environment}" if self.install else self.environment
        return f"{self.repo} / {self.branch}" if self.branch else self.repo
