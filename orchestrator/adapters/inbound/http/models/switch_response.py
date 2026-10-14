from pydantic import BaseModel


class SwitchResponse(BaseModel):
    prompt: str
    hidden: bool
