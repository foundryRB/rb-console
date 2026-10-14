from pydantic import BaseModel


class DriverIn(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str | None = None
