"""Immutable execution identity and opaque executor input."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    name: str
    run_id: str
    repository: str
    executor_payload: str
