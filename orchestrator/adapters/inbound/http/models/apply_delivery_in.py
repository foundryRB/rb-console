from pydantic import BaseModel


class ApplyDeliveryIn(BaseModel):
    target: str
    model: str | None = None
