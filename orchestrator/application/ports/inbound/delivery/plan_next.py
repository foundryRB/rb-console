"""PlanNext application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.delivery.next_action import NextAction
from orchestrator.domain.model.run_config import RunConfig


@runtime_checkable
class PlanNextPort(Protocol):
    def execute(self, repo: str, config: RunConfig) -> NextAction: ...
