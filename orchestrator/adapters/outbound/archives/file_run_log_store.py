"""FileRunLogStore: run-log snapshots on the Console's data volume. The compiled Workflow
GC's a finished run's pods a bounded time after completion (podGC + deleteDelayDuration),
so the live log read goes dark long before the run's row leaves the list (ttlStrategy
keeps rows for days). The service captures each terminal run's pod-prefixed tail here
once, and log reads fall back to it. Two files per run, keyed by the Workflow name: the
log tail and the run's retained record (its row and graph). Both are reclaimed past the
prune horizon on write - the horizon sits well past the Workflow TTL, so no run still
listed ever loses its files first.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import asdict

from orchestrator.adapters.outbound.archives.execution_archive_codec import (
    decode_execution,
)
from orchestrator.domain.exceptions.retained_evidence_unreadable import (
    RetainedEvidenceUnreadable,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.retained_execution import RetainedExecution

_PRUNE_AFTER_SECONDS = (
    30 * 24 * 3600
)  # default horizon; callers pass the live retention setting


class FileRunLogStore:
    def __init__(self, root: str | None = None) -> None:
        self._root = root or os.environ.get("FC_RUN_LOG_DIR", "/data/run-logs")

    def save(
        self, name: str, text: str, prune_after_seconds: int | None = None
    ) -> None:
        """Persist one run's log text (idempotent overwrite), then prune files past the
        horizon - the caller's (the run rows' own TTL, so files and rows expire
        together), or this store's default when none is given."""
        self._save_text(self._path(name), text)
        self._prune(prune_after_seconds or _PRUNE_AFTER_SECONDS)

    def load(self, name: str) -> str | None:
        """The stored text for a run, or None when no snapshot exists."""
        try:
            with open(self._path(name), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def has(self, name: str) -> bool:
        """A cheap existence probe, so the capture sweep never re-reads stored runs."""
        return os.path.exists(self._path(name))

    def save_metadata(self, name: str, metadata: RetainedExecution) -> None:
        self._save_text(
            self._path(name) + ".json", json.dumps(asdict(metadata), sort_keys=True)
        )

    def _save_text(self, path: str, text: str) -> None:
        temporary: str | None = None
        try:
            os.makedirs(self._root, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._root,
                prefix=".capture-",
                suffix=".pending",
                delete=False,
            ) as stream:
                temporary = stream.name
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            if os.name == "posix":
                directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        except OSError as exc:
            raise SourceUnavailable("Run evidence archive is unavailable.") from exc
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def all_metadata(self) -> list[RetainedExecution]:
        """Every retained run record. A record that cannot be decoded withholds only itself:
        the read refuses with RetainedEvidenceUnreadable, which carries every record it did
        read, so the archive never passes for complete and never hides the readable rest."""
        rows: list[RetainedExecution] = []
        unreadable: list[str] = []
        try:
            with os.scandir(self._root) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.endswith(".log.json"):
                        try:
                            stream = open(entry.path, encoding="utf-8")
                        except FileNotFoundError:
                            continue  # reclaimed by a prune since the scan listed it
                        with stream:
                            try:
                                rows.append(decode_execution(json.load(stream)))
                            except (ValueError, TypeError):
                                unreadable.append(entry.name)
        except FileNotFoundError as exc:
            if not os.path.exists(self._root):
                return []
            raise SourceUnavailable(
                "Retained execution evidence is unavailable."
            ) from exc
        except OSError as exc:
            raise SourceUnavailable(
                "Retained execution evidence is unreadable."
            ) from exc
        if unreadable:
            raise RetainedEvidenceUnreadable(tuple(sorted(unreadable)), tuple(rows))
        return rows

    def _path(self, name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        return os.path.join(self._root, f"{safe}.log")

    def _prune(self, prune_after_seconds: int) -> None:
        """Reclaim every run past the horizon. A log file goes with its run record, so the
        archive never lists a run whose log is gone; a record with no log file ages out on
        its own mtime, which each tick that still lists the run refreshes."""
        horizon = time.time() - prune_after_seconds
        try:
            # Judge the whole scan before removing anything: a record removed with its log
            # may still be ahead in the scan, and a file another writer removed is skipped.
            expired: list[str] = []
            for entry in os.scandir(self._root):
                if not entry.is_file() or not entry.name.endswith((".log", ".log.json")):
                    continue
                try:
                    if entry.stat().st_mtime >= horizon:
                        continue
                except FileNotFoundError:
                    continue
                expired.append(entry.path)
                if entry.name.endswith(".log"):
                    expired.append(entry.path + ".json")
            for path in expired:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(path)
        except OSError:
            logging.getLogger(__name__).warning(
                "Run log retention cleanup failed", exc_info=True
            )
