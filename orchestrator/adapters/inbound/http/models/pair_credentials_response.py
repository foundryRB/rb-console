from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.pair_credential import PairCredential


class PairCredentialsResponse(BaseModel):
    credentials: list[PairCredential]
