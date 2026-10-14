from pydantic import BaseModel


class GitIdentityIn(BaseModel):
    name: str
    email: str = ""
    login: str = ""
    token: str | None = None
