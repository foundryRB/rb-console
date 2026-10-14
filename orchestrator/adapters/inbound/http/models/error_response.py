from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: str
    operation_key: str | None = None
