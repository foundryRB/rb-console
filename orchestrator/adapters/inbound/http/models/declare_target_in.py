from pydantic import BaseModel


class DeclareTargetIn(BaseModel):
    """One target as the operator declared it in the pane."""

    repo: str
    name: str
    kind: str
    install: str = ""
    environment: str = ""
    branch: str = ""
    credential: str = ""
    probe_url: str = ""
    author: str = ""
    pair_repo: str = ""
