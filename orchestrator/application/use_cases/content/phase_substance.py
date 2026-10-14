"""Read selected phase content through bounded content and studio contracts."""

from __future__ import annotations

import yaml

from orchestrator.application.ports.inbound.content.repo_file import RepoFilePort
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.services.identity.slug import helper_slug


class PhaseSubstance:
    def __init__(
        self, *, studios: StudioGateway | None, cap_repo_file: RepoFilePort, cap_status: StatusPort
    ) -> None:
        self.studios = studios
        self.cap_repo_file = cap_repo_file
        self.cap_status = cap_status

    def execute(self, repo: str, phase: str) -> dict:
        definition = self.cap_status.execute(repo).lifecycle
        selected = next((item for item in definition.phases if item.name == phase), None)
        if selected is None:
            return {}
        if selected.artifact == "proposal" and self.studios is not None:
            return self.studios.scope_substance(helper_slug(repo), studio=selected.studio)
        if selected.artifact == "design" and self.studios is not None:
            return self.studios.design_substance(helper_slug(repo), studio=selected.studio)
        if selected.artifact != "handoff":
            return {}
        text = self.cap_repo_file.execute(repo, "intent.yaml").content
        payload = yaml.safe_load(text) if text else None
        if not isinstance(payload, dict):
            return {}
        claims = []
        for key, value in payload.items():
            if str(key).startswith("INT-") and isinstance(value, dict):
                claims.append(
                    {
                        "id": str(key),
                        "status": str(value.get("status") or ""),
                        "criticality": str(value.get("criticality") or ""),
                        "statement": str(value.get("statement") or ""),
                    }
                )
        return {"claims": claims} if claims else {}
