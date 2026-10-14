from pydantic import BaseModel


class PairCredentialIn(BaseModel):
    """A repo-host credential for the far side of a pair, as the operator registers it: the
    name a `kind: repository` promotion target declares, the host it reaches, and the secret
    that pair granted us. Registration, not minting - the token belongs to their organization."""

    name: str
    host: str = ""
    login: str = ""
    token: str | None = None
