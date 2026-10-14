"""A bounded response body owned by the transport."""
from io import BytesIO


class BufferedResponse(BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str], status: int) -> None:
        super().__init__(body)
        self.headers = headers
        self.status = status
