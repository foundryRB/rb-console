from pydantic import BaseModel


class ReadyResponse(BaseModel):
    ready: bool
