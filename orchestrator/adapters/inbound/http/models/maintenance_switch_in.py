from pydantic import BaseModel


class MaintenanceSwitchIn(BaseModel):
    repo: str
    number: int
