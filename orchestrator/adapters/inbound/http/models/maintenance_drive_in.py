from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.config_in import ConfigIn


class MaintenanceDriveIn(BaseModel):
    repo: str
    act: str
    target: int | None = None
    mode: str | None = None
    config: ConfigIn = ConfigIn()
