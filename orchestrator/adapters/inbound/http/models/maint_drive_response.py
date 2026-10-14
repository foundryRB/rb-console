from pydantic import BaseModel


class MaintDriveResponse(BaseModel):
    run_id: str
    handle: str | None
    act: str
    mode: str
