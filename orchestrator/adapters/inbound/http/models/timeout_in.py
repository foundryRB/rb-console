from pydantic import BaseModel


class TimeoutIn(BaseModel):
    target: str
    timeout_hours: float
