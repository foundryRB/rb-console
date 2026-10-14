from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.role_def import RoleDef


class RolesResponse(BaseModel):
    roles: dict[str, str]
    catalog: list[RoleDef]
