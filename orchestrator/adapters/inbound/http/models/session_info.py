from __future__ import annotations

from pydantic import BaseModel


class SessionInfo(BaseModel):
    oidc_enabled: bool
    sign_out_url: str
    #: Whether the install serves several teams, each seeing its own projects.
    teams_enabled: bool = False
    #: Whether the caller is an admin: every project, and the team settings.
    admin: bool = True
    #: The teams the caller belongs to.
    teams: list[str] = []
    #: How the caller is shown: the signed-in email, else the operator's name.
    user: str = ""
