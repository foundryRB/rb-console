from pydantic import BaseModel


class PromotionDriveIn(BaseModel):
    """Perform one declared target's door. The release is optional: unnamed, the act carries
    what the entry environment proved, which is what the pane already shows as proven."""

    repo: str
    target: str
    release: str = ""
