"""McpDoors over consumed application contracts."""

from __future__ import annotations

from orchestrator.domain.services.delivery_launch import mcp_doors as _mcp_doors


class McpDoors:
    def __init__(self) -> None:
        pass

    def execute(self) -> list[str]:
        """The MCP doors a worker may connect to. The settings pane reads this so the
        door list is never a hand-maintained copy of the phase->studio map."""
        return _mcp_doors()
