"""Redirects preserve the API authority and read method."""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp, code: int, msg: str, headers, newurl: str) -> Request | None:
        if req.get_method() != "GET" or urlsplit(newurl).scheme != "https" or urlsplit(newurl).netloc != urlsplit(req.full_url).netloc:
            raise SourceUnavailable("GitHub redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)
