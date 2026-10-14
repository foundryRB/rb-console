from pydantic import BaseModel


class MaintenanceCloseIn(BaseModel):
    repo: str
    number: int
