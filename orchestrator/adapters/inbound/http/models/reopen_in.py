from pydantic import BaseModel


class ReopenIn(BaseModel):
    target: str
    phase: str
