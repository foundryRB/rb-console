from pydantic import BaseModel


class TeamIn(BaseModel):
    name: str
    group: str
