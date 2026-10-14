from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.tree_entry import TreeEntry


class TreeResponse(BaseModel):
    tree: list[TreeEntry]
