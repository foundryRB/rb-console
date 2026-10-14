from pydantic import BaseModel


class ResumeResponse(BaseModel):
    handle: str
    resumed: str
