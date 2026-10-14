from pydantic import BaseModel


class GitRolesIn(BaseModel):
    roles: dict[str, str] = {}
