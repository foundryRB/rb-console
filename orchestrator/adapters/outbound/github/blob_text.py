"""Decode GitHub's ASCII-whitespace-folded base64 file representation."""
from __future__ import annotations

import base64
from collections.abc import Mapping

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


def blob_text(blob: Mapping[str, object]) -> str:
    """Require valid base64 and complete UTF-8 after removing ASCII folding."""
    try:
        content = blob["content"]
        if not isinstance(content, str):
            raise TypeError("GitHub blob content must be text")
        encoded = content.encode("ascii").translate(None, b" \t\r\n\v\f")
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceUnavailable("GitHub blob content is malformed") from exc
