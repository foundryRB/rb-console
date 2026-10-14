from pydantic import BaseModel


class ApplyDriverIn(BaseModel):
    model: str = ""
