from pydantic import BaseModel


class RunLogsResponse(BaseModel):
    handle: str
    logs: str
