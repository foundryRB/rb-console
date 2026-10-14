from pydantic import BaseModel


class PromotionDriveResponse(BaseModel):
    run_id: str
    handle: str | None
    target: str
    release: str
    kind: str
