"""A credential the console resolves once and holds, instead of re-deriving per call.

Resolving the console's git token is a four-hop walk through the config store - which
identity holds the 'console' role, that identity's fields, its Secret's existence, its
value - and every hop is a live read. The adapters call the provider on EVERY GitHub
read (``_get`` resolves before each request), so one 40-repo inbox sweep resolved it
~520 times and, against the K8s store, spawned ~2600 ``kubectl`` processes to answer the
same question. That cost bought nothing: the answer only changes when the operator
changes it. Worse, it bought a fault - each hop degrades to "" on a failed read, so a
single flaky read made a configured console look UNCONFIGURED, and an org scan that read
"no token" returned an empty fleet indistinguishable from an empty org.

So the resolution is held here. Late binding is preserved where it was actually wanted:
a Settings write that can change the credential invalidates the hold (``invalidate``),
so a rotation still takes effect with no redeploy. The TTL is only a backstop for a
change made AROUND the Console - editing the Secret with kubectl - which the Settings
path cannot announce.

Two rules keep the hold honest:

  - An empty resolution is NEVER held. A console that starts before its identity is
    assigned must keep asking, not cache the absence.
  - An empty resolution NEVER evicts a held value, and does not restamp it. A token
    does not spontaneously become empty; an empty read is overwhelmingly a FAILED read,
    and treating it as "the operator removed the credential" is the exact confusion that
    emptied the board. The next call retries. Removal is announced through
    ``invalidate``, where an empty answer is authoritative.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

#: How long a held credential is served before it is re-resolved. Only a backstop for an
#: out-of-band edit; a Settings write invalidates the hold outright, so this is not the
#: bound on how fast a rotation takes effect.
_TTL_SECONDS = 300.0


class HeldCredential:
    """One credential, resolved on demand and held. ``get`` is the provider the outbound
    adapters take - it stays a plain ``() -> str`` callable, so no adapter learns that a
    credential is cached at all."""

    def __init__(self, resolve: Callable[[], str], ttl: float = _TTL_SECONDS) -> None:
        self._resolve = resolve
        self._ttl = ttl
        self._lock = threading.Lock()
        self._value = ""
        self._at = 0.0

    def get(self) -> str:
        """The credential. Resolves only when nothing is held or the hold has aged out;
        a resolution that comes back empty leaves any held value standing and is retried
        on the next call rather than cached."""
        with self._lock:
            if self._value and (time.monotonic() - self._at) < self._ttl:
                return self._value
            try:
                fresh = self._resolve() or ""
            except Exception:  # noqa: BLE001  a failed resolve reads exactly like an empty one
                fresh = ""
            if fresh:
                self._value = fresh
                self._at = time.monotonic()
            return fresh or self._value

    def invalidate(self) -> None:
        """Drop the hold: the next ``get`` re-resolves and its answer is authoritative,
        empty included. Called from every Settings write that can change which credential
        the console runs as, so a rotation - or a revocation - takes effect at once."""
        with self._lock:
            self._value = ""
            self._at = 0.0
