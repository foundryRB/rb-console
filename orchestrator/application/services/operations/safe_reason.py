"""A failure's own words, made safe to log, keep on a receipt and return to the caller."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"(gh[opsu]_|github_pat_|sk-ant-)[A-Za-z0-9_\-]{8,}")
_URL_CREDENTIALS = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@")
_QUERY = re.compile(r"(https?://[^\s?]+)\?\S*")


def safe_reason(exc: BaseException, *, named: bool = True, limit: int = 300) -> str:
    """The exception's message, led by its class when ``named``, with token-shaped strings,
    URL credentials and query strings removed and the length bounded (INT-FC-R190). The
    console's own messages name what failed; this keeps a wrapped library message from
    carrying a secret along with it."""
    message = " ".join(str(exc).split())
    text = f"{type(exc).__name__}: {message}" if named and message else message or type(exc).__name__
    text = _TOKEN.sub("[redacted]", text)
    text = _URL_CREDENTIALS.sub(r"\1[redacted]@", text)
    text = _QUERY.sub(r"\1?[redacted]", text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _origin(exc: BaseException) -> BaseException | None:
    """What the exception was raised from: its explicit cause, else the exception it was
    raised during unless `raise ... from None` hid that one on purpose."""
    if exc.__cause__ is not None:
        return exc.__cause__
    return None if exc.__suppress_context__ else exc.__context__


def safe_causes(exc: BaseException, *, depth: int = 3) -> str:
    """The safe reasons of what the exception was raised from, nearest first. A cause a
    raise hid with `from None` (a timeout whose text is a command line, say) stays hidden."""
    reasons = []
    cause = _origin(exc)
    while cause is not None and len(reasons) < depth:
        reasons.append(safe_reason(cause))
        cause = _origin(cause)
    return "; ".join(reasons)
