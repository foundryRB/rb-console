from pydantic import BaseModel


class EstablishIn(BaseModel):
    target: str
    request: str = ""
    source_archive: str = ""
    source_name: str = ""
    app_name: str = ""
    #: The team the line belongs to; a member of one team may leave it empty.
    team: str = ""
