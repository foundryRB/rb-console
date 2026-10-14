from pydantic import BaseModel


class SettingResponse(BaseModel):
    configured: bool
    fields: dict[str, str] = {}
