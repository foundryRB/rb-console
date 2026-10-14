from pydantic import BaseModel


class MaintenanceCommentIn(BaseModel):
    repo: str
    number: int
    body: str
