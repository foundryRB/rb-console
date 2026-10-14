from pydantic import BaseModel


class RoleDef(BaseModel):
    key: str
    label: str
    agent: str = ""
    kind: str
