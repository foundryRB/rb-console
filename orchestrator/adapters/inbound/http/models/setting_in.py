from pydantic import BaseModel


class SettingIn(BaseModel):
    fields: dict[str, str] = {}
    secret: str | None = None
