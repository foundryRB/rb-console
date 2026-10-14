from __future__ import annotations

from pydantic import BaseModel


class ProtoScreen(BaseModel):
    slug: str
    name: str
    html: str
    css: str
