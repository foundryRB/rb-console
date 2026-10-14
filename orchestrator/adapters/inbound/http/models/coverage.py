from pydantic import BaseModel


class Coverage(BaseModel):
    complete: bool
    observed: int
    total: int | None
