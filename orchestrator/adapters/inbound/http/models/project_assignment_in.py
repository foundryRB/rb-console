from pydantic import BaseModel


class ProjectAssignmentIn(BaseModel):
    repository: str
    #: The team the project belongs to; empty leaves it unassigned.
    team: str = ""
