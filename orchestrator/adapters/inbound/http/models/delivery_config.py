from __future__ import annotations

from pydantic import BaseModel


class DeliveryConfig(BaseModel):
    mode: str
    provider: str
    base_url: str
    model: str
    agent: str
    #: The applied agent's level, and the team or person who owns it.
    agent_level: str = ""
    agent_owner: str = ""
    timeout_hours: float
    credentialed: bool
