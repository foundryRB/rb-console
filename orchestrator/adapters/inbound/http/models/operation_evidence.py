from pydantic import BaseModel


class OperationEvidence(BaseModel):
    repository: str | None = None
    handle: str | None = None
    resource_version: str | None = None
    uid: str | None = None
