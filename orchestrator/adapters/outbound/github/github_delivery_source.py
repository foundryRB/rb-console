from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import replace
from urllib.parse import quote

from orchestrator.adapters.outbound.github.blob_text import blob_text
from orchestrator.adapters.outbound.github.delivery_contract import (
    REF_NAMESPACE,
    _anomalous,
)
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.adapters.outbound.records.lifecycle_codec import decode_pin
from orchestrator.adapters.outbound.records.yaml_record_parser import parse_record
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.delivery import (
    JOURNAL,
    SCRATCH,
    SEQUENCE,
    demo_source_name,
    derive_seed,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.delivery_record import DeliveryRecord
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.repository_file import RepositoryFile
from orchestrator.domain.model.repository_inventory_entry import (
    RepositoryInventoryEntry,
)
from orchestrator.domain.model.repository_tree_entry import RepositoryTreeEntry
from orchestrator.domain.services.delivery_resolution import derive_from_records


class GitHubDeliverySource:
    _API = "https://api.github.com"
    # The four phase records plus the journal: not a record, but its frontmatter
    # carries Learn's ``learned:`` stamp, which the resolver derives from too.
    _RECORDS = frozenset(p.record for p in SEQUENCE) | {JOURNAL}

    def __init__(self, org: str, token_provider, *, transport: GitHubTransport | None = None, inventory_provider=None) -> None:
        self._transport = transport or GitHubTransport()
        self._inventory_provider = inventory_provider
        self._org = org
        self._token_provider = token_provider  # callable -> the live git token

    def scan(self) -> list[DeliveryState]:
        """Discover deliveries the way the contract defines one: a repo carrying a live
        ``delivery/*`` scratch ref (INT-FC-R31, decision 0003), never a repo topic.
        Enumerate the org's repos (the same list the Fleet view joins on) and probe each
        with ONE matching-refs call; a repo whose namespace is empty is not a delivery,
        one ref resolves the line (its records are read from the ref's branch root), and
        more than one surfaces as an anomaly state rather than a silent pick. State is
        derived with the same pure function the local and single-repo paths use, so all
        three agree. An unavailable repository raises a typed source failure, so the
        collector retains the last complete fleet observation with stale coverage.

        The probes fan out on a small thread pool: each repo is one independent GET
        (plus the root listing and record blobs for the few that are deliveries), and
        serial they cost a fresh TLS round-trip apiece - the bulk of the rescan the
        operator sat behind (issue #46). Eight workers keeps the burst well under
        GitHub's secondary limits; ``map`` keeps the org's order."""
        token = self._token_provider() or ""
        if not token:
            # No git credential: nothing to discover WITH, which is not the same as
            # nothing to discover. Raising keeps the index's last-known deliveries
            # standing instead of replacing them with an inferred emptiness (R144).
            raise SourceUnavailable("no git credential is configured for the console role")
        inventory = self.list_org_repos()
        identities = {r.repository: r.repository_id for r in inventory}
        names = list(identities)

        def probe(full_name: str) -> DeliveryState | None:
            try:
                refs = self._line_refs(full_name, token)
            except SourceUnavailable:
                raise
            except (urllib.error.HTTPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                raise SourceUnavailable("delivery observation could not be read") from exc
            if not refs:
                return None  # no delivery/* ref: not a delivery
            if len(refs) > 1:
                return _anomalous(full_name, [r["name"] for r in refs])
            ref = refs[0]["name"]
            try:
                listing = self._get(f"/repos/{full_name}/contents?ref={quote(refs[0]['sha'] or ref, safe='')}", token)
            except SourceUnavailable:
                raise
            except (urllib.error.HTTPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                raise SourceUnavailable("delivery observation could not be read") from exc
            definition = self._definition_of(full_name, listing, token, refs[0]["sha"] or ref)
            state = derive_from_records(full_name, True, self._collect(full_name, listing, token, refs[0]["sha"] or ref, definition), definition)
            seed, demo_of = self._seed_of(full_name, token)
            return replace(state, scratch_ref=ref, seed=seed, demo_of=demo_of, revision=refs[0]["sha"], repository_id=identities[full_name])

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(copy_context().run, probe, name) for name in names]
            return [s for future in futures if (s := future.result()) is not None]

    def _seed_of(self, full: str, token: str) -> tuple[str, str]:
        """What the line grows from, read off the repo's tags and nothing declared
        (INT-FC-R149): a ``delivered/<slug>/P<n>`` tag reads follow-on, a ``seed/<slug>``
        tag reads recast, neither reads new. Two namespaced matching-refs reads are paid
        only by a repository carrying a live line. An unreadable namespace raises a
        typed source failure, so unavailable evidence never implies new.

        A repo named ``demo-<x>`` reads one thing more (INT-FC-R153): whether the org holds
        ``<x>`` as a line, a ``delivery/*`` head or a ``delivered/*`` tag on it. It does, and
        the line is a demo of it (REF-Demo), the source's full name riding beside the seed;
        it does not, and the prefix is just a name. An unreadable source raises a typed
        failure, so unavailable evidence never implies an ordinary line."""
        try:
            delivered = self._get(f"/repos/{full}/git/matching-refs/tags/delivered/", token)
            seeded = self._get(f"/repos/{full}/git/matching-refs/tags/seed/", token)
        except SourceUnavailable:
            raise
        except (urllib.error.HTTPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SourceUnavailable("delivery seed could not be read") from exc
        if not isinstance(delivered, list) or not isinstance(seeded, list):
            raise SourceUnavailable("delivery seed inventory is malformed")
        demo_of = self._demo_source_of(full, token)
        seed = derive_seed(
            has_delivered_tag=isinstance(delivered, list) and bool(delivered),
            has_seed_tag=isinstance(seeded, list) and bool(seeded),
            demo_source=demo_of,
        )
        return seed, demo_of

    def _demo_source_of(self, full: str, token: str) -> str:
        """The line a ``demo-<x>`` repo rehearses: ``owner/<x>`` when the org holds it as a
        line, or "" when the name carries no prefix or the source is confirmed absent.
        Unavailable source evidence raises a typed failure. HTTP 404 confirms absence."""
        name = demo_source_name(full)
        if not name:
            return ""
        source = f"{full.split('/')[0]}/{name}"
        try:
            heads = self._get(f"/repos/{source}/git/matching-refs/heads/delivery/", token)
            tags = self._get(f"/repos/{source}/git/matching-refs/tags/delivered/", token)
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return ""
            raise SourceUnavailable("demo source could not be read") from err
        except SourceUnavailable:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SourceUnavailable("demo source is malformed") from exc
        if not isinstance(heads, list) or not isinstance(tags, list):
            raise SourceUnavailable("demo source inventory is malformed")
        is_line = (isinstance(heads, list) and bool(heads)) or (isinstance(tags, list) and bool(tags))
        return source if is_line else ""

    def state_of(self, repo: str) -> DeliveryState:
        token = self._token_provider() or ""
        full = repo if "/" in repo else f"{self._org}/{repo}"
        if not token:
            raise SourceUnavailable("GitHub credential unavailable")
        try:
            refs = self._line_refs(full, token)
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return derive_from_records(full, False, {})
            raise SourceUnavailable("delivery namespace could not be read") from exc
        except OSError as exc:
            raise SourceUnavailable("delivery namespace could not be read") from exc
        if not refs:
            return derive_from_records(full, False, {})  # no delivery/* ref: not a delivery
        if len(refs) > 1:
            return _anomalous(full, [r["name"] for r in refs])
        ref = refs[0]["name"]
        try:
            listing = self._get(f"/repos/{full}/contents?ref={quote(refs[0]['sha'] or ref, safe='')}", token)
        except SourceUnavailable:
            raise
        except (urllib.error.HTTPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SourceUnavailable("delivery records could not be read") from exc
        definition = self._definition_of(full, listing, token, refs[0]["sha"] or ref)
        state = derive_from_records(full, True, self._collect(full, listing, token, refs[0]["sha"] or ref, definition), definition)
        info = self._get(f"/repos/{full}", token)
        repository_id = str(info.get("id") or "")
        if not repository_id:
            raise SourceUnavailable("repository identity is unavailable")
        seed, demo_of = self._seed_of(full, token)
        return replace(state, scratch_ref=ref, seed=seed, demo_of=demo_of, revision=refs[0]["sha"], repository_id=repository_id)

    def read_config(self, repo: str, *, revision: str = "") -> dict:
        token = self._token_provider() or ""
        full = repo if "/" in repo else f"{self._org}/{repo}"
        if not token:
            raise SourceUnavailable("GitHub credential unavailable")
        try:
            ref = revision or self._single_ref(full, token)
            if ref is None:
                return {}
            blob = self._get(f"/repos/{full}/contents/config.json?ref={quote(ref, safe='')}", token)
            data = json.loads(blob_text(blob))
            if not isinstance(data, dict):
                raise SourceUnavailable("delivery config is malformed")
            return data
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {}
            raise SourceUnavailable("delivery config could not be read") from exc
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SourceUnavailable("delivery config is malformed") from exc

    def present_records(self, repo: str) -> list[str]:
        token = self._token_provider() or ""
        full = repo if "/" in repo else f"{self._org}/{repo}"
        if not token:
            raise SourceUnavailable("GitHub credential unavailable")
        try:
            ref = self._single_ref(full, token)
            if ref is None:
                return []
            listing = self._get(f"/repos/{full}/contents?ref={quote(ref, safe='')}", token)
        except SourceUnavailable:
            raise
        except (urllib.error.HTTPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SourceUnavailable("delivery record inventory could not be read") from exc
        names = {e.get("name") for e in (listing if isinstance(listing, list) else [])}
        return [p.record for p in SEQUENCE if p.record in names]

    def content_revision(self, repo: str, path: str = "") -> str:
        token = self._token_provider() or ""
        if not token:
            raise SourceUnavailable("no git credential is configured")
        full = repo if "/" in repo else f"{self._org}/{repo}"
        if path.startswith(f"{SCRATCH}/"):
            refs = self._line_refs(full, token)
            if len(refs) != 1 or not refs[0]["sha"]:
                raise SourceUnavailable("scratch revision is unavailable")
            return refs[0]["sha"]
        info = self._get(f"/repos/{full}", token)
        branch = info.get("default_branch")
        if not branch:
            raise SourceUnavailable("default branch is unavailable")
        data = self._get(f"/repos/{full}/git/ref/heads/{quote(branch, safe='')}", token)
        sha = (data.get("object") or {}).get("sha", "")
        if not sha:
            raise SourceUnavailable("repository revision is unavailable")
        return sha

    def tree(self, repo: str, *, revision: str = "", scratch_revision: str = "") -> list[RepositoryTreeEntry]:
        token = self._token_provider() or ""
        if not token:
            raise SourceUnavailable("no git credential is configured")
        full = repo if "/" in repo else f"{self._org}/{repo}"
        revision = revision or self.content_revision(repo)
        data = self._get(f"/repos/{full}/git/trees/{quote(revision, safe='')}?recursive=1", token)
        out = self._tree_entries(data)
        if scratch_revision:
            scratch = self._get(f"/repos/{full}/git/trees/{quote(scratch_revision, safe='')}?recursive=1", token)
            out.append(RepositoryTreeEntry(SCRATCH, "directory"))
            out.extend(self._tree_entries(scratch, SCRATCH + "/"))
        return out

    @staticmethod
    def _tree_entries(data: object, prefix: str = "") -> list[RepositoryTreeEntry]:
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            raise SourceUnavailable("repository tree is malformed")
        if data.get("truncated"):
            raise SourceUnavailable("repository tree exceeds the complete read limit")
        kinds = {"blob": "file", "tree": "directory", "commit": "submodule"}
        entries = []
        for row in data["tree"]:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str) or not row["path"] or row.get("type") not in kinds:
                raise SourceUnavailable("repository tree entry is malformed")
            size = row.get("size")
            if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
                raise SourceUnavailable("repository tree entry is malformed")
            entries.append(RepositoryTreeEntry(prefix + row["path"], kinds[row["type"]], size))
        return entries

    def file(self, repo: str, path: str, *, revision: str = "") -> RepositoryFile:
        token = self._token_provider() or ""
        if not token:
            raise SourceUnavailable("no git credential is configured")
        full = repo if "/" in repo else f"{self._org}/{repo}"
        revision = revision or self.content_revision(repo, path)
        rel = path[len(SCRATCH) + 1:] if path.startswith(f"{SCRATCH}/") else path
        blob = self._get(f"/repos/{full}/contents/{quote(rel, safe='/')}?ref={quote(revision, safe='')}", token)
        content = blob_text(blob)
        size = blob.get("size", len(content.encode("utf-8")))
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise SourceUnavailable("repository file size is malformed")
        return RepositoryFile(path, content, size)

    def list_org_repos(self) -> list[RepositoryInventoryEntry]:
        """Complete repository inventory; unavailable evidence raises SourceUnavailable."""
        if self._inventory_provider is not None:
            return self._inventory_provider()
        token = self._token_provider() or ""
        if not token:
            raise SourceUnavailable("no git credential is configured for the console role")
        try:
            data = self._get(f"/orgs/{self._org}/repos?per_page=100&sort=pushed", token)
            if not isinstance(data, list):
                raise SourceUnavailable("repository inventory is malformed")
            entries = []
            for row in data:
                if not isinstance(row, dict):
                    raise SourceUnavailable("repository inventory entry is malformed")
                repository = row.get("full_name")
                topics = row.get("topics") or []
                updated_at = row.get("pushed_at")
                if (not isinstance(repository, str) or len(repository.split("/")) != 2
                        or not all(repository.split("/")) or not isinstance(topics, list)
                        or any(not isinstance(topic, str) for topic in topics)
                        or (updated_at is not None and not isinstance(updated_at, str))):
                    raise SourceUnavailable("repository inventory entry is malformed")
                if row.get("archived"):
                    continue
                entries.append(RepositoryInventoryEntry(
                    repository=repository, name=repository.split("/")[1],
                    updated_at=updated_at, topics=tuple(topics),
                    repository_id=str(row.get("id") or ""),
                ))
            return entries
        except (urllib.error.HTTPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SourceUnavailable("the repository inventory could not be read") from exc

    def _line_refs(self, full: str, token: str) -> list[dict]:
        """Every ``delivery/*`` branch on the repo - name (short form) and tip sha - via
        ONE matching-refs call, the whole per-repo discovery probe. Raises on a transport
        error; the callers decide what an unreadable repo means for their read. A repository
        with no commits is GitHub's definite answer that it carries no ref at all, so it
        reads as none (INT-FC-R01), never as unreadable."""
        try:
            data = self._get(f"/repos/{full}/git/matching-refs/heads/{REF_NAMESPACE}", token)
        except urllib.error.HTTPError as exc:
            if exc.code == 409 and self._empty_repository(exc):
                return []
            raise
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise SourceUnavailable("delivery ref inventory is malformed")
        refs: list[dict] = []
        for r in data:
            name = r.get("ref") or ""
            if name.startswith(f"refs/heads/{REF_NAMESPACE}"):
                refs.append(
                    {
                        "name": name[len("refs/heads/"):],
                        "sha": ((r.get("object") or {}).get("sha") or ""),
                    }
                )
        return refs

    @staticmethod
    def _empty_repository(exc: urllib.error.HTTPError) -> bool:
        """Whether a 409 is GitHub's "Git Repository is empty." rather than another conflict."""
        try:
            body = json.loads(exc.read() or b"{}")
        except (OSError, ValueError):
            return False
        return isinstance(body, dict) and str(body.get("message") or "").startswith("Git Repository is empty")

    def _single_ref(self, full: str, token: str) -> str | None:
        """The line's one scratch ref name, or None when the repo carries none or more
        than one (the anomaly belongs to the state read; substance reads just go empty)."""
        refs = self._line_refs(full, token)
        return refs[0]["name"] if len(refs) == 1 else None

    def _get(self, path: str, token: str):
        return self._transport.json(f"{self._API}{path}", token, paginate=True)

    def _definition_of(self, full: str, listing, token: str, ref: str) -> LifecycleDefinition:
        entries = listing if isinstance(listing, list) else []
        entry = next((item for item in entries if item.get("name") == "config.json"), None)
        if entry is None:
            return CURRENT_LIFECYCLE
        path = f"/repos/{full}/git/blobs/{entry['sha']}" if entry.get("sha") else f"/repos/{full}/contents/config.json?ref={quote(ref, safe='')}"
        blob = self._get(path, token)
        try:
            config = json.loads(blob_text(blob))
        except (TypeError, ValueError) as exc:
            raise SourceUnavailable("line lifecycle pin is unavailable") from exc
        if not isinstance(config, dict):
            raise SourceUnavailable("line lifecycle pin is unavailable")
        if "lifecycle" not in config:
            return CURRENT_LIFECYCLE
        return decode_pin(config["lifecycle"])

    def _collect(self, full_name: str, listing, token: str, ref: str, definition: LifecycleDefinition = CURRENT_LIFECYCLE) -> dict[str, DeliveryRecord]:
        contents: dict[str, DeliveryRecord] = {}
        for entry in listing if isinstance(listing, list) else []:
            name = entry.get("name", "")
            if name not in {p.record for p in definition.phases}:
                continue
            try:
                blob = self._get(
                    f"/repos/{full_name}/git/blobs/{entry['sha']}" if entry.get("sha") else
                    f"/repos/{full_name}/contents/{name}?ref={quote(ref, safe='')}", token
                )
                contents[name] = parse_record(blob_text(blob))
            except SourceUnavailable:
                raise
            except (urllib.error.HTTPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                raise SourceUnavailable("committed record could not be read") from exc
        return contents
