from pydantic import BaseModel


class ProjectAssignment(BaseModel):
    repository: str
    team: str
