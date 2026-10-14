from pydantic import BaseModel


class CloseIn(BaseModel):
    target: str
