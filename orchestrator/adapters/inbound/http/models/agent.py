from __future__ import annotations

from pydantic import BaseModel


class Agent(BaseModel):
    name: str
    provider: str
    base_url: str
    model: str
    models: list[str]
    configured: bool
    #: install, team or user: who the agent serves.
    level: str = "install"
    #: The team a team agent serves, or the person a user agent belongs to.
    owner: str = ""
    #: Whether the caller may apply the agent to a line.
    usable: bool = True
    #: Whether the caller may edit or delete the agent.
    manageable: bool = True
