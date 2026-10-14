"""RunConfig domain value."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.run_mode import RunMode


@dataclass(frozen=True)
class RunConfig:
    """Execution mode, repository authority and the selected worker's runtime budget."""

    worker_credential: str | None
    repo_target: str | None
    repo_rights: bool = False
    mode: RunMode = RunMode.INTERACTIVE
    # Endpoint overrides apply to Anthropic-compatible worker providers.
    worker_provider: str = "claude"
    worker_base_url: str = ""
    worker_model: str = ""
    # Per-phase wall-clock budget, mapped to Argo activeDeadlineSeconds.
    worker_timeout_seconds: int = 3600

    def missing(self) -> tuple[str, ...]:
        gaps: list[str] = []
        if not self.worker_credential:
            gaps.append("worker_credential")
        if not self.repo_target:
            gaps.append("repo_target")
        if not self.repo_rights:
            gaps.append("repo_rights")
        return tuple(gaps)

    @property
    def complete(self) -> bool:
        return not self.missing()
