from pydantic import BaseModel


class AppActionResponse(BaseModel):
    name: str
    paused: bool
