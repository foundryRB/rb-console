from pydantic import BaseModel


class Team(BaseModel):
    name: str
    #: The identity-provider group whose members belong to the team.
    group: str
    #: The projects assigned to the team, as `owner/name`.
    repositories: list[str] = []
