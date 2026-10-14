"""Acknowledged repository command result."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommentCreated:
    comment_id: int
    url: str = ""
