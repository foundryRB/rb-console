"""ToolUrls over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition


class ToolUrls:
    def __init__(self, *, studios: StudioGateway | None) -> None:
        self.studios = studios

    def execute(self, definition: LifecycleDefinition) -> dict[str, str]:
        """Map each phase's declared studio to its east-west base URL for the gate
        stamper's export, which the compiler hands the worker as FC_TOOL_URL (INT-FC-R151).
        Empty when no studio gateway is wired or it cannot name the door; a tooled gate's
        stamp then refuses rather than signs over an unfrozen export."""
        gateway = self.studios
        if gateway is None:
            return {}
        out: dict[str, str] = {}
        for studio in sorted({phase.studio for phase in definition.phases if phase.studio}):
            try:
                url = gateway.tool_url(studio)
            except Exception:  # noqa: BLE001 - boundary failure is logged or propagated
                url = ""
            if url:
                out[studio] = url
        return out
