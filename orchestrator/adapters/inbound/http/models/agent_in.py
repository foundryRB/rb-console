from pydantic import BaseModel


class AgentIn(BaseModel):
    name: str
    provider: str = "claude"
    base_url: str = ""
    model: str = ""
    credential: str | None = None
    models: list[str] = []
    #: install (everyone, admins add it), team (that team's members) or user (yours alone).
    level: str = "install"
    #: The team a team agent serves.
    team: str = ""
