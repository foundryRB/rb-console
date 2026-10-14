from pydantic import BaseModel


class ModelIn(BaseModel):
    target: str
    provider: str = "claude"
    base_url: str = ""
    model: str = ""
    credential: str | None = None
    timeout_hours: float | None = None
