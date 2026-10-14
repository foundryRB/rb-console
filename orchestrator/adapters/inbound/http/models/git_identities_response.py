from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.git_identity import GitIdentity


class GitIdentitiesResponse(BaseModel):
    identities: list[GitIdentity]
