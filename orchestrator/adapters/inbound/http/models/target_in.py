from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.config_in import ConfigIn


class TargetIn(BaseModel):
    target: str
    config: ConfigIn = ConfigIn()
    from_phase: str | None = None
    feedback: str | None = None
