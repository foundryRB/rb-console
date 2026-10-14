from pydantic import BaseModel


class StopResponse(BaseModel):
    handle: str
    shutdown: str
