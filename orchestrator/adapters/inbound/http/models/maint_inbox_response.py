from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.maint_inbox_item import MaintInboxItem


class MaintInboxResponse(BaseModel):
    items: list[MaintInboxItem]
    scanned: bool

    freshness: Freshness | None = None
