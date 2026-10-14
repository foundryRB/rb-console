from pydantic import BaseModel


class MergeResponse(BaseModel):
    sha: str
    merged: bool
    message: str
