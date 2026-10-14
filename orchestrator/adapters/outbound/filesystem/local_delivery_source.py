from __future__ import annotations

import json
from pathlib import Path

from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from orchestrator.adapters.outbound.records.lifecycle_codec import decode_pin
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.delivery import SCRATCH, SEQUENCE
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.repository_file import RepositoryFile
from orchestrator.domain.model.repository_inventory_entry import (
    RepositoryInventoryEntry,
)
from orchestrator.domain.model.repository_tree_entry import RepositoryTreeEntry


class LocalDeliverySource:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def scan(self) -> list[DeliveryState]:
        if not self._root.is_dir():
            return []
        return [
            derive_state(str(p), self._definition(str(p)))
            for p in sorted(self._root.iterdir())
            if (p / SCRATCH).is_dir()
        ]

    def state_of(self, repo: str) -> DeliveryState:
        if not (Path(repo) / SCRATCH).is_dir():
            return derive_state(repo)
        return derive_state(repo, self._definition(repo))

    def _definition(self, repo: str) -> LifecycleDefinition:
        config = self.read_config(repo)
        if not isinstance(config, dict):
            raise SourceUnavailable("line lifecycle pin is unavailable")
        if "lifecycle" not in config:
            return CURRENT_LIFECYCLE
        return decode_pin(config["lifecycle"])

    def read_config(self, repo: str, *, revision: str = "") -> dict:
        path = Path(repo) / SCRATCH / "config.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise SourceUnavailable("line configuration could not be read") from exc

    def present_records(self, repo: str) -> list[str]:
        scratch = Path(repo) / SCRATCH
        return [p.record for p in SEQUENCE if (scratch / p.record).is_file()]

    def content_revision(self, repo: str, path: str = "") -> str:
        import hashlib
        root = Path(repo)
        selected = [root / path] if path else sorted(root.rglob("*"))
        digest = hashlib.sha256()
        for item in selected:
            if item.is_file() and ".git" not in item.parts:
                digest.update(str(item.relative_to(root)).encode())
                digest.update(item.read_bytes())
        return digest.hexdigest()

    def tree(self, repo: str, *, revision: str = "", scratch_revision: str = "") -> list[RepositoryTreeEntry]:
        root = Path(repo)
        if not root.is_dir():
            return []
        out = []
        for p in sorted(root.rglob("*")):
            if ".git" in p.parts:
                continue
            out.append(RepositoryTreeEntry(
                str(p.relative_to(root)).replace("\\", "/"),
                "directory" if p.is_dir() else "file",
                p.stat().st_size if p.is_file() else None,
            ))
        return out

    def file(self, repo: str, path: str, *, revision: str = "") -> RepositoryFile:
        fp = Path(repo) / path
        if not fp.is_file():
            return RepositoryFile(path, "", 0)
        text = fp.read_text(encoding="utf-8", errors="replace")
        return RepositoryFile(path, text, len(text.encode("utf-8")))

    def list_org_repos(self) -> list[RepositoryInventoryEntry]:
        return []
