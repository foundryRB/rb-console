from pydantic import BaseModel


class MaintenanceMergeIn(BaseModel):
    repo: str
    pr: int
