"""PromotionOptions over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.services.promotion.entry_environments import (
    helper_entry_environments,
)


class CollectPromotionOptions:
    def __init__(self, *, psource: PromotionSource | None) -> None:
        self.psource = psource

    def execute(self, repo: str) -> dict:
        """What this app could declare a target on: every install it is onboarded
        to, and each install's environments as its deploy branch carries them.

        Read from the app's own repo, so the form offers only destinations that
        exist. The entry environment of each install is excluded: it is deployed
        automatically, and a promotion into it would be overwritten.
        """
        if self.psource is None:
            return {"repo": repo, "installs": [], "readable": False}
        installs = self.psource.deploy_installs(repo)
        entry = partial(helper_entry_environments)(repo, installs)
        return {
            "repo": repo,
            "readable": bool(installs),
            "installs": [
                {
                    "install": install,
                    "entry": entry.get(install, ""),
                    "environments": [
                        env for env in environments if env != entry.get(install, "")
                    ],
                }
                for install, environments in sorted(installs.items())
            ],
        }
