from pydantic import BaseModel


class DeliveryConfigIn(BaseModel):
    target: str
    mode: str = "interactive"
