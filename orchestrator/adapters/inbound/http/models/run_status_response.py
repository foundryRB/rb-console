from pydantic import BaseModel


class RunStatusResponse(BaseModel):
    handle: str
    phase: str
