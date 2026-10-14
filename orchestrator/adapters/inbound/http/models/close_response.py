from pydantic import BaseModel


class CloseResponse(BaseModel):
    number: int
    state: str
