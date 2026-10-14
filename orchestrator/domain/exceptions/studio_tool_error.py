"""StudioToolError domain value."""
from __future__ import annotations


class StudioToolError(RuntimeError):
    """A named studio refusal, carried by the REST error field or MCP error text."""

    _KNOWN = (
        "AlreadyExistsError",
        "SyncFailedError",
        "PrFailedError",
        "InvalidAppNameError",
    )
    def __init__(self, studio: str, tool: str, detail: str, error_name: str = "") -> None:
        super().__init__(f"{studio}.{tool} refused: {detail}")
        self.studio = studio
        self.tool = tool
        self.detail = detail
        self._error_name = error_name

    @property
    def error(self) -> str:
        if self._error_name:
            return self._error_name
        return next((name for name in self._KNOWN if self.detail.startswith(name + ":")), "")
