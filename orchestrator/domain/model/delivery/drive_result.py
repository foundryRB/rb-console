"""Delivery execution result."""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.delivery_state import DeliveryState


@dataclass(frozen=True)
class DriveResult:
    """The outcome of compiling a delivery's remaining line and submitting it to the
    executor (Argo). Deterministic up to the submit; the executor then owns retries,
    timeouts, and the gate suspends.
    """

    run_id: str
    state: DeliveryState
    workflow: CompiledWorkflow
    handle: str | None = None
