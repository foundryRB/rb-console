from pydantic import BaseModel


class PairCredential(BaseModel):
    name: str
    host: str
    login: str
    configured: bool
