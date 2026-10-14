from pydantic import BaseModel


class CommentResponse(BaseModel):
    id: int
    html_url: str
