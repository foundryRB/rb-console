from pydantic import BaseModel


class ConfigIn(BaseModel):
    worker_credential: str | None = None
    repo_target: str | None = None
    repo_rights: bool = False
    worker_provider: str = "claude"
    worker_base_url: str = ""
    worker_model: str = ""
