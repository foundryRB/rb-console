"""Immutable approved promotion execution inputs."""

from dataclasses import dataclass

from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.promotion_target import PromotionTarget


@dataclass(frozen=True)
class PreparedPromotionCommand:
    workflow: CompiledWorkflow
    run_id: str
    target: PromotionTarget
    release: str
    source_revision: str
    repository_id: str
