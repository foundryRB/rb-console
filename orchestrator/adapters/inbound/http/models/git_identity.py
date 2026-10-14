from pydantic import BaseModel


class GitIdentity(BaseModel):
    name: str
    email: str
    login: str
    configured: bool
