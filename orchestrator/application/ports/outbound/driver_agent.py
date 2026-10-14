"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

__all__ = ["DriverAgent"]


class DriverAgent(Protocol):
    def configured(self) -> bool:
        """Whether a driver credential is set (the co-pilot chat is otherwise a hint)."""
        ...

    def model(self) -> str:
        """The model the chat will use (the cheapest Claude by default)."""
        ...

    def chat(self, system: str, messages: list[dict], max_tokens: int = 1024) -> str:
        """One turn of the co-pilot chat: a system prompt plus the message history, returning
        the assistant's reply. Raises if no credential is configured."""
        ...

    def validate(
        self, credential: str, model: str = "", base_url: str = ""
    ) -> bool | None:
        """A lightweight authenticated preflight against the resolved endpoint, using the
        same auth selection chat() does. True on a working credential, False on an explicit
        401/403 answer (fail-closed on an answer), None on a transport failure or timeout
        (fail-open - unreachable is not evidence the credential itself is wrong)."""
        ...
