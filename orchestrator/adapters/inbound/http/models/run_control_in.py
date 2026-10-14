from pydantic import BaseModel


class RunControlIn(BaseModel):
    handle: str
    terminate: bool = False
