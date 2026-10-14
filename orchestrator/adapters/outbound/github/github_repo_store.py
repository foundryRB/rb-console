"""RepoStore over the GitHub API: create the delivery repo in the org and mint the
line's scratch ref with its skeleton, all with the shared git token. No local clone and
no PVC: creation is API calls, discovery reads the org for a live ``delivery/*`` ref
(the DeliverySource), and each worker clones its own copy. The scratch lives on ONE
orphan ``delivery/<line-id>`` branch per repo, records at the branch root
(decision 0003): every scratch read here follows that resolved ref and every write
names it, and a repo whose ref cannot be resolved surfaces a distinct error rather than
an empty read. ``list_delivery_repos`` is unused (the DeliveryIndex lists deliveries);
this store's job is create-and-register. A repo carries no discovery topic: its scratch
ref is what marks it a delivery (INT-FC-R31).
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

from orchestrator.adapters.outbound.github.blob_text import blob_text
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.adapters.outbound.records.lifecycle_codec import (
    encode_lifecycle,
    encode_pin,
)
from orchestrator.adapters.outbound.records.yaml_record_parser import (
    parse as _parse_front,
)
from orchestrator.adapters.outbound.studios.http_studio_gateway import internal_base_url
from orchestrator.domain.delivery import (
    RECAST_DIR,
    SCRATCH,
    delivery_slug,
)
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.repository_identity import RepositoryIdentity
from orchestrator.domain.model.source_file import SourceFile

_API = "https://api.github.com"

# The playbook's gate stamper: the single deterministic stamp every runner executes
# (REF-Delivery section 1, "How a gate closes"; anti-pattern 30 - never hand-port it).
# Baked into the image from the playbook repo; FC_STAMP_HELPER overrides for local runs.
_STAMP_HELPER = os.environ.get("FC_STAMP_HELPER", "/opt/foundry/stamp_gate.py")

# The playbook's record helper: the deterministic writer of the record's frontmatter
# block (its own docstring - the phase authors the body, this helper owns the block).
# The cockpit's Re-open is a write of that block, so it runs the helper rather than
# editing the fields itself (anti-pattern 30). FC_REACH_HELPER overrides for local runs.
_REACH_HELPER = os.environ.get("FC_REACH_HELPER", "/opt/foundry/reach_gate.py")

# The scratch skeleton is loaded from the pinned playbook helper and written through
# the GitHub API.
_ESTABLISH_HELPER = os.environ.get("FC_ESTABLISH_HELPER", "/opt/foundry/establish_scratch.py")


def _establish_module():
    """The scratch helper as an importable module.

    Loaded on use, not at import: an absent helper is a resolution not yet done
    (the image bakes it in, FC_ESTABLISH_HELPER overrides locally), and it should
    surface where it is needed rather than break every import of this adapter."""
    spec = importlib.util.spec_from_file_location("fc_establish_scratch", _ESTABLISH_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"the scratch helper is not at {_ESTABLISH_HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Required helper evidence copied into the synthesized scratch. The stamper requires
# the journal alongside the canonical record (REF-Delivery section 1).
_SEEDED_READS = ("journal.md",)

# Gate exports read the phase's declared studio through its configured internal door.


def _pending_gate(text: str) -> str:
    """Clear a canonical record signature while preserving its body bytes."""
    front = _parse_front(text)
    if front is None or not front.gate:
        raise ValueError("a canonical gate record is required")
    lines = text.splitlines(keepends=True)
    end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    for index in range(1, end):
        if re.match(r"^signed:\s*", lines[index]):
            lines[index] = "signed: pending\n"
            return "".join(lines)
    lines.insert(end, "signed: pending\n")
    return "".join(lines)


def _request_doc(request: str) -> str:
    """The customer's verbatim request, the ground truth the Scope phase reads
    (REF-Delivery section 2). Not a phase record, so it does not affect derived progress.

    The helper's own function: a line opened here and one opened at a desk read
    identically because they are the same bytes, not two authors agreeing."""
    return _establish_module().request_doc(request)


class GitHubRepoStore:
    def __init__(self, org: str, token_provider, *, transport: GitHubTransport | None = None, inventory_provider=None) -> None:
        self._transport = transport or GitHubTransport()
        self._inventory_provider = inventory_provider
        self._org = org
        self._token_provider = token_provider

    def list_delivery_repos(self) -> list[str]:
        return []  # discovery is the DeliveryIndex's job (GitHubDeliverySource)

    def ensure(self, target: str) -> str:
        name = target.split("/")[-1]
        token = self._require_token()
        self._create_repo(name, token)  # idempotent: skip if it already exists
        return f"{self._org}/{name}"

    def repo_exists(self, target: str) -> bool:
        """Whether the org already holds this repo under this exact name: the same read
        ensure() branches create-vs-adopt on, answered BEFORE the branch happens (#67).
        A caller that must tell an adopt from a creation has no other handle - ensure()
        does both and says nothing about which - and the two are different acts."""
        name = target.split("/")[-1].strip()
        if not name:
            return False
        return self._holds(name, self._require_token())

    def repository_identity(self, repository: str) -> RepositoryIdentity | None:
        full = repository if "/" in repository else f"{self._org}/{repository}"
        try:
            data = self._req("GET", f"/repos/{full}", self._require_token())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise SourceUnavailable("repository identity could not be read") from exc
        if not isinstance(data, dict):
            raise SourceUnavailable("repository identity response is invalid")
        if str(data.get("full_name") or "").lower() != full.lower():
            return None
        try:
            return RepositoryIdentity(str(data["full_name"]), str(data["id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable("repository identity response is invalid") from exc

    def register(
        self,
        workspace: str,
        request: str = "",
        source: Sequence[SourceFile] = (),
        source_name: str = "",
    ) -> None:
        """Create or adopt one scratch ref with the pinned helper's skeleton.

        Capture the request once. A new recast stores its source beneath _recast/
        and retains its register commit with an annotated seed tag. An existing live
        line accepts adoption but refuses source seeding."""
        token = self._require_token()
        full = workspace if "/" in workspace else f"{self._org}/{workspace}"
        refs = self._line_refs(full, token)
        if len(refs) > 1:
            raise RuntimeError(
                f"{full} carries {len(refs)} delivery/* refs; exactly one may exist - "
                "remove the extras before registering"
            )
        self._ensure_scratch_ignored(full, token)
        if refs:
            if source:
                raise RuntimeError(
                    f"{full} already carries a live line ({refs[0]['name']}); a source lands "
                    "only on a scratch minted in this establish - close that line first"
                )
            # Adopt the existing line. The request still lands if it never was captured.
            ref = refs[0]["name"]
            if request and not self._exists(full, "request.md", token, ref=ref):
                self._put_file(
                    full,
                    "request.md",
                    _request_doc(request),
                    "delivery: capture the customer request",
                    token,
                    branch=ref,
                )
            return
        # Line identifiers use the install's local calendar date.
        ref = f"delivery/{datetime.datetime.now().astimezone().date().isoformat()}"
        entries = [
            {"path": "README.md", "mode": "100644", "type": "blob",
             "content": _establish_module().SKELETON},
        ]
        if request:
            entries.append(
                {"path": "request.md", "mode": "100644", "type": "blob",
                 "content": _request_doc(request)}
            )
        # The recast source, under _recast/ on the scratch and nowhere else. Text rides
        # inline; a binary (an image, a font) goes up as a base64 blob first and is
        # referenced by sha, because the trees API takes only UTF-8 inline content.
        for file in source:
            path = f"{RECAST_DIR}/{file.path}"
            text = file.text
            if text is not None:
                entries.append({"path": path, "mode": "100644", "type": "blob", "content": text})
                continue
            blob = self._req(
                "POST", f"/repos/{full}/git/blobs", token,
                {"content": base64.b64encode(file.data).decode(), "encoding": "base64"},
            )
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        message = f"delivery: register (establish the {ref} scratch ref)"
        if source:
            label = source_name.strip() or "the uploaded archive"
            message += f"; recast source from {label} ({len(source)} files under {RECAST_DIR}/)"
        try:
            tree = self._req("POST", f"/repos/{full}/git/trees", token, {"tree": entries})
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                # The git-data API answers 409 on a repository with no commits at all.
                raise RuntimeError(
                    f"{full} has no commits, so the git-data API cannot mint the scratch "
                    "ref: create the repo through establish (which auto-initialises it) "
                    "or push an initial commit, then register again"
                ) from exc
            raise
        commit = self._req(
            "POST", f"/repos/{full}/git/commits", token,
            {"message": message, "tree": tree["sha"], "parents": []},
        )
        self._req(
            "POST", f"/repos/{full}/git/refs", token,
            {"ref": f"refs/heads/{ref}", "sha": commit["sha"]},
        )
        if source:
            # The seed is a fact about the line from here on, read the way a delivered
            # phase is read: off a tag. ``seed/<slug>`` on the register commit, annotated
            # with the register message, is one matching-refs read per line for the
            # console and the app's provenance for good (INT-FC-R149). It outlives the
            # scratch ref close removes, so the source stays reachable under it.
            tag_name = f"seed/{delivery_slug(full)}"
            tag = self._req(
                "POST", f"/repos/{full}/git/tags", token,
                {"tag": tag_name, "message": message, "object": commit["sha"], "type": "commit"},
            )
            self._req(
                "POST", f"/repos/{full}/git/refs", token,
                {"ref": f"refs/tags/{tag_name}", "sha": tag["sha"]},
            )


    def _ensure_scratch_ignored(self, full: str, token: str) -> None:
        """Ensure the default branch's .gitignore carries the ``.delivery/`` line. The
        scratch mounts there as a linked worktree, and an unignored mount point is a
        gitlink trap: a whole-tree ``git add`` on the default branch stages ``.delivery``
        as a gitlink, and once that gitlink is committed every later worker's
        ``git worktree add`` fails on the occupied path, terminally parking the line.
        Idempotent: a .gitignore already carrying the line is left untouched, so an
        adopted repo pays one read and a scaffolded one pays nothing extra."""
        sha = None
        content = ""
        try:
            blob = self._req("GET", f"/repos/{full}/contents/.gitignore", token)
            content = blob_text(blob)
            sha = blob.get("sha")
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise SourceUnavailable("gitignore could not be read") from exc
            content = ""
        if re.search(r"^\.delivery/?\s*$", content, re.MULTILINE):
            return
        addition = (
            "# The delivery scratch's worktree mount point (committed on the line's "
            "delivery/* ref, never here).\n.delivery/\n"
        )
        text = (content.rstrip("\n") + "\n\n" + addition) if content.strip() else addition
        body: dict = {
            "message": "delivery: ignore the scratch mount point",
            "content": base64.b64encode(text.encode()).decode(),
        }
        if sha:
            body["sha"] = sha
        self._req("PUT", f"/repos/{full}/contents/.gitignore", token, body)

    def write_gate(self, workspace: str, record: str, date: str, *, definition: LifecycleDefinition, expected_revision: str = "") -> None:
        """Stamp the canonical record through the pinned playbook helper.

        Read the record and required evidence at the approved scratch commit. The
        helper validates the pending signature and recorded review, exports studio
        artifacts through the configured internal tool URL, and produces the stamped
        files. Commit all changed files together with the approved commit as parent;
        a non-forced ref update rejects a concurrent head change. Helper refusals
        surface as ValueError with the helper's reason."""
        phase = next((item for item in definition.phases if item.record == record), None)
        if phase is None:
            raise ValueError("the gate record is outside the effective definition")
        token = self._require_token()
        full = workspace if "/" in workspace else f"{self._org}/{workspace}"
        ref = self._require_line_ref(full, token)
        tip = self._assert_revision(full, ref, token, expected_revision)
        blob = self._req("GET", f"/repos/{full}/contents/{record}?ref={quote(tip, safe='')}", token)
        content = blob_text(blob)
        with tempfile.TemporaryDirectory() as tmp:
            # The helper resolves the studio project from this delivery-named root.
            root = Path(tmp) / delivery_slug(full)
            scratch = root / SCRATCH
            scratch.mkdir(parents=True)
            (scratch / record).write_text(content, encoding="utf-8")
            definition_path = root / "lifecycle.json"
            definition_path.write_text(json.dumps(encode_lifecycle(definition)), encoding="utf-8")
            seeded = self._seed_scratch(full, scratch, record, token, tip)
            argv = [
                sys.executable, _STAMP_HELPER,
                "--repo", str(root), "--record", record, "--date", date,
                "--definition", str(definition_path),
                "--by", "the operator (console Sign)",
            ]
            studio = phase.studio
            if studio:
                argv += ["--tool-url", internal_base_url(studio)]
            result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", check=False)
            if result.returncode != 0:
                reason = (result.stdout or result.stderr or "").strip()
                raise ValueError(reason or "the gate helper refused the stamp")
            written = self._scratch_changes(scratch, seeded)
        stamped = written.pop(record, None)
        if stamped is None:
            raise ValueError("the gate helper reported success but left the record unstamped")
        written[record] = stamped
        self._commit_revision(full, ref, tip, written, f"delivery: sign gate ({date})", token)


    def _seed_scratch(self, full: str, scratch: Path, record: str, token: str, ref: str) -> dict[str, str]:
        """Copy the files the gate helper reads into the synthesized scratch; return every
        seeded path mapped to the content seeded, so ``_scratch_changes`` can tell what the
        helper wrote from what it was handed.

        A file absent UPSTREAM stays absent here: that is a real state the helper is
        entitled to refuse on (a line with no journal captured nothing), and inventing one
        to get past the check would forge the evidence the check exists to demand."""
        seeded = {record: (scratch / record).read_text(encoding="utf-8")}
        for name in _SEEDED_READS:
            try:
                blob = self._req(
                    "GET", f"/repos/{full}/contents/{name}?ref={quote(ref, safe='')}", token
                )
            except SourceUnavailable:
                raise
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise SourceUnavailable("gate helper evidence could not be read") from exc
                blob = {}
            if not blob:
                continue
            text = blob_text(blob)
            path = scratch / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            seeded[name] = text
        return seeded

    @staticmethod
    def _scratch_changes(scratch: Path, seeded: dict[str, str]) -> dict[str, str]:
        """Every scratch file the helper created or changed, repo-relative path -> content.
        Compared against what was seeded rather than listed blindly, so an untouched
        journal is not re-committed on every Sign."""
        changed: dict[str, str] = {}
        for path in sorted(p for p in scratch.rglob("*") if p.is_file()):
            rel = path.relative_to(scratch).as_posix()
            text = path.read_text(encoding="utf-8")
            if seeded.get(rel) != text:
                changed[rel] = text
        return changed

    def _put_scratch_file(self, full: str, path: str, content: str, message: str, token: str, ref: str) -> None:
        """PUT one scratch file onto the line's ref (branch-root path, ``branch:`` named
        explicitly), carrying the blob sha when the path already exists there - the
        contents API rejects an update without it, and the sha has to be the REF's, so
        the existence probe follows the ref too."""
        body: dict = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": ref,
        }
        try:
            blob = self._req("GET", f"/repos/{full}/contents/{path}?ref={quote(ref, safe='')}", token)
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise SourceUnavailable("scratch content could not be read") from exc
            blob = {}
        if blob.get("sha"):
            body["sha"] = blob["sha"]
        self._req("PUT", f"/repos/{full}/contents/{path}", token, body)

    def reopen_gate(self, workspace: str, record: str, *, expected_revision: str = "") -> None:
        """Re-open a phase: un-sign its gate and hand the record back to the record helper
        as opened-for-work, in one write on the line's scratch ref. The resolver then reads
        the gate as pending and the line parks there; downstream records are untouched
        (nothing deleted) and read as present-but-stale until each is re-signed forward."""
        token = self._require_token()
        full = workspace if "/" in workspace else f"{self._org}/{workspace}"
        ref = self._require_line_ref(full, token)
        tip = self._assert_revision(full, ref, token, expected_revision)
        blob = self._req("GET", f"/repos/{full}/contents/{record}?ref={quote(tip, safe='')}", token)
        content = blob_text(blob)
        self._commit_revision(full, ref, tip, {record: self._reopened(record, content)}, "delivery: re-open gate (un-sign)", token)

    @staticmethod
    def _reopened(record: str, content: str) -> str:
        """Reopen a canonical record through its pinned deterministic helper."""
        pending = _pending_gate(content)
        front = _parse_front(pending)
        names = {
            "--phase": front.phase if front else "",
            "--skill": front.skill if front else "",
            "--gate": front.gate if front else "",
        }
        blank = [flag.lstrip("-") for flag, value in names.items() if not value]
        if blank:
            raise ValueError(
                f"{record} names no {', '.join(blank)} and is no phase record of the "
                "delivery line, so the record helper has nothing to open it as"
            )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scratch = root / SCRATCH
            scratch.mkdir(parents=True)
            (scratch / record).write_text(pending, encoding="utf-8")
            argv = [
                sys.executable, _REACH_HELPER,
                "--repo", str(root), "--record", record, "--status", "in-progress",
            ]
            for flag, value in names.items():
                argv += [flag, value]
            result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", check=False)
            if result.returncode != 0:
                reason = (result.stdout or result.stderr or "").strip()
                raise ValueError(reason or "the record helper refused to re-open the record")
            return (scratch / record).read_text(encoding="utf-8")

    def append_journal(self, workspace: str, entry: str) -> None:
        """Append an entry to the scratch journal (creating it if absent), on the line's
        ref. The gate review's second outcome writes here: sign stamps a date
        (write_gate), re-drive journals the operator's feedback - durable BEFORE the run
        is live, so the review conversation survives whatever the re-driven worker
        rewrites."""
        token = self._require_token()
        full = workspace if "/" in workspace else f"{self._org}/{workspace}"
        ref = self._require_line_ref(full, token)
        path = "journal.md"
        content = "# Delivery journal\n\nThe line's running trail: lessons, defects, and gate reviews.\n"
        sha = None
        try:  # append when it already exists (needs the blob sha, read off the ref)
            blob = self._req("GET", f"/repos/{full}/contents/{path}?ref={quote(ref, safe='')}", token)
            content = blob_text(blob)
            sha = blob.get("sha")
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise SourceUnavailable("journal could not be read") from exc
            sha = None
        # An identical journal tail is idempotent. Repeated content elsewhere in the
        # journal records a distinct entry and is appended.
        if content.rstrip("\n").endswith(entry.strip()):
            return
        body = {
            "message": "delivery: journal a gate review (re-drive with feedback)",
            "content": base64.b64encode(
                (content.rstrip("\n") + "\n\n" + entry.strip() + "\n").encode()
            ).decode(),
            "branch": ref,
        }
        if sha:
            body["sha"] = sha
        self._req("PUT", f"/repos/{full}/contents/{path}", token, body)

    def write_config(self, workspace: str, config: dict, *, lifecycle: LifecycleDefinition | None = None) -> None:
        """Persist the scratch config.json (mode, and the captured lifecycle when given) on
        the line's ref. It travels with the delivery, so any worker or tool reads the same
        delivery-level truth."""
        if lifecycle is not None:
            config = {**config, "lifecycle": encode_pin(lifecycle)}
        token = self._require_token()
        full = workspace if "/" in workspace else f"{self._org}/{workspace}"
        ref = self._require_line_ref(full, token)
        path = "config.json"
        text = json.dumps(config, indent=2) + "\n"
        body = {
            "message": "delivery: pin the line lifecycle definition" if lifecycle is not None else "delivery: set mode",
            "content": base64.b64encode(text.encode()).decode(),
            "branch": ref,
        }
        try:  # update in place when it already exists (needs the blob sha, read off the ref)
            existing = self._req("GET", f"/repos/{full}/contents/{path}?ref={quote(ref, safe='')}", token)
            if "content" in existing and blob_text(existing) == text:
                # Unchanged: no empty commit, so the line's revision (which every later
                # command is checked against) stays where the operator last read it.
                return
            body["sha"] = existing.get("sha")
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise SourceUnavailable("scratch config could not be read") from exc
            body.pop("sha", None)
        self._req("PUT", f"/repos/{full}/contents/{path}", token, body)

    def close_line(self, workspace: str, *, expected_revision: str = "") -> None:
        """Anchor the approved scratch tip, then compare-delete its branch.

        The annotated delivered tag retains the record trail and the build's attested
        default-branch SHA. GitHub's updateRefs takes commit ids only, so the tag's ref,
        which points at the annotated tag object, is created through the REST refs API
        first; updateRefs then deletes the branch only while it still points at the
        approved tip. No live ref is removed until its approved history has a delivered
        tag: a branch that moved meanwhile keeps its branch, and the tag anchors the tip
        that was approved.
        """
        token = self._require_token()
        full = workspace if "/" in workspace else f"{self._org}/{workspace}"
        refs = self._line_refs(full, token)
        if not refs:
            return  # already closed: nothing to tag, nothing to delete
        if len(refs) > 1:
            names = ", ".join(sorted(r["name"] for r in refs))
            raise ValueError(
                f"{full} carries more than one delivery/* scratch ref ({names}); "
                "exactly one may exist - refusing to close a silent pick"
            )
        ref, tip = refs[0]["name"], refs[0]["sha"]
        if not tip:
            raise SourceUnavailable("scratch revision is unavailable")
        self._assert_revision(full, ref, token, expected_revision or tip)
        tag_name = f"delivered/{delivery_slug(full)}/{self._delivered_phase(full, tip, token)}"
        existing_ref = self._tag_state(full, tag_name, token)
        existing = existing_ref[1] if existing_ref else None
        repository = self._req("GET", f"/repos/{full}", token)
        if not isinstance(repository, dict) or not isinstance(repository.get("node_id"), str) or not repository["node_id"] or str(repository.get("full_name", "")).lower() != full.lower():
            raise SourceUnavailable("close repository identity is unavailable")
        if existing is None:
            message = f"delivery: close line ({tag_name} anchors the {ref} record trail)"
            attests = self._attested_sha(full, tip, token)
            if attests:
                # The annotation is the whole delivered marker a follow-on reads:
                # existence, phase, date, and the attested default-branch SHA - all off
                # the tag OBJECT, never its tree (REF-FollowOn).
                message += f"\n\nattests: {attests}"
            tag = self._req(
                "POST", f"/repos/{full}/git/tags", token,
                {
                    "tag": tag_name,
                    "message": message,
                    "object": tip,
                    "type": "commit",
                },
            )
            if not isinstance(tag, dict) or not tag.get("sha"):
                raise SourceUnavailable("annotated close tag could not be confirmed")
            self._create_tag_ref(full, tag_name, tag["sha"], tip, token)
        elif existing != tip:
            # A colliding delivered tag retains its existing history and requires operator
            # resolution before this line can close.
            raise ValueError(
                f"the tag {tag_name} already exists and points at {existing}, not this "
                f"line's tip {tip}; refusing to close over it - move or delete the "
                "existing tag first"
            )
        # The tag anchors the approved tip (created now, or by an earlier attempt that
        # stopped before the delete), so the branch may go, and only at that tip.
        self._atomic_close_refs(
            repository["node_id"],
            [{"name": f"refs/heads/{ref}", "beforeOid": tip, "afterOid": "0" * 40}],
            token,
        )

    def _create_tag_ref(self, full: str, tag_name: str, tag_sha: str, tip: str, token: str) -> None:
        """Point the delivered tag's ref at its annotated tag object (INT-FC-R179). The REST
        refs API refuses a ref that already exists, so a tag another close created meanwhile
        is accepted only when it anchors the same tip; a refusal with no such tag (a rule
        that forbids the tag, say) is GitHub's, and stops the close."""
        try:
            made = self._req(
                "POST", f"/repos/{full}/git/refs", token,
                {"ref": f"refs/tags/{tag_name}", "sha": tag_sha},
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 422:
                raise SourceUnavailable("the delivered tag could not be created") from exc
            raced = self._tag_state(full, tag_name, token)
            if raced is None:
                raise SourceUnavailable("GitHub refused the delivered tag") from exc
            if raced[1] != tip:
                raise Conflict(
                    "another close created the delivered tag meanwhile, on another tip"
                ) from exc
            return
        target = made.get("object") if isinstance(made, dict) else None
        if not isinstance(target, dict) or target.get("sha") != tag_sha:
            raise SourceUnavailable("the delivered tag could not be confirmed")

    def _atomic_close_refs(self, repository_id: str, updates: list[dict], token: str) -> None:
        """GitHub updateRefs compares every ref and changes them atomically; it takes commit
        ids only, never a tag object."""
        marker = hashlib.sha256(json.dumps([repository_id, updates], sort_keys=True).encode()).hexdigest()
        result = self._req("POST", "/graphql", token, {
            "query": "mutation CloseLine($input: UpdateRefsInput!) { updateRefs(input: $input) { clientMutationId } }",
            "variables": {"input": {"repositoryId": repository_id, "refUpdates": updates, "clientMutationId": marker}},
        })
        if not isinstance(result, dict):
            raise SourceUnavailable("atomic close result is unavailable")
        if result.get("errors"):
            errors = result["errors"]
            if not isinstance(errors, list) or any(not isinstance(error, dict) for error in errors):
                raise SourceUnavailable("atomic close result is malformed")
            if any(error.get("type") in {"RATE_LIMITED", "SERVICE_UNAVAILABLE", "FORBIDDEN", "UNAUTHORIZED"} for error in errors):
                raise SourceUnavailable("GitHub could not authorize or complete atomic close")
            raise Conflict("GitHub refused atomic close; a ref changed or the update was rejected")
        data = result.get("data")
        closed = data.get("updateRefs") if isinstance(data, dict) else None
        if not isinstance(closed, dict) or closed.get("clientMutationId") != marker:
            raise SourceUnavailable("atomic close outcome could not be confirmed")

    def _tag_state(self, full: str, tag_name: str, token: str) -> tuple[str, str] | None:
        """Read the ref object OID and its commit target, or confirmed absence.

        Annotated tag objects are dereferenced to their commit. Only HTTP 404 means
        absence; other failures stop the close."""
        try:
            ref = self._req("GET", f"/repos/{full}/git/ref/tags/{tag_name}", token)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        obj = ref.get("object") or {}
        if obj.get("type") == "tag" and obj.get("sha"):
            tag = self._req("GET", f"/repos/{full}/git/tags/{obj['sha']}", token)
            return obj["sha"], ((tag.get("object") or {}).get("sha")) or ""
        return obj.get("sha") or "", obj.get("sha") or ""

    def _attested_sha(self, full: str, ref: str, token: str) -> str:
        """The default-branch SHA the line's build record attested live (its ``attests:``
        frontmatter field), read from the scratch ref so the close carries it into the
        tag annotation - a follow-on reads the delivered marker (existence, phase, date,
        attests) from the tag object alone, never the tag's tree. Empty when build.md or
        the field is absent: a line abandoned before build closes without one, because
        absence is honest and a fabricated value is not. Only a 404 counts as absent;
        any other read failure aborts the close, since a transient error must not mint
        a permanently wrong annotation."""
        try:
            blob = self._req(
                "GET", f"/repos/{full}/contents/build.md?ref={quote(ref, safe='')}", token
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return ""
            raise
        text = blob_text(blob)
        match = re.search(r"^attests:\s*[\"']?([0-9a-fA-F]{7,40})\b", text, re.MULTILINE)
        return match.group(1) if match else ""

    def _delivered_phase(self, full: str, ref: str, token: str) -> str:
        """The ``P<n>`` the line delivered, read from the proposal record's ``delivers:``
        field on the scratch ref - the one place the phase pin is authoritative. ``P1``
        when the record or the field is absent (a line closed before scope pinned one
        still gets a well-formed tag). Only a 404 counts as absent: any other read
        failure aborts the close, because a transient error must not mint a permanently
        mislabeled tag."""
        try:
            blob = self._req(
                "GET", f"/repos/{full}/contents/proposal.md?ref={quote(ref, safe='')}", token
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return "P1"
            raise
        text = blob_text(blob)
        match = re.search(r"^delivers:\s*[\"']?(P\d+)", text, re.MULTILINE | re.IGNORECASE)
        return match.group(1) if match else "P1"

    def _line_refs(self, full: str, token: str) -> list[dict]:
        """Every ``delivery/*`` branch on the repo (short name + tip sha), via one
        matching-refs call - the store's read of the singleton scratch-ref invariant."""
        data = self._req("GET", f"/repos/{full}/git/matching-refs/heads/delivery/", token)
        refs: list[dict] = []
        for r in data if isinstance(data, list) else []:
            name = r.get("ref") or ""
            if name.startswith("refs/heads/delivery/"):
                refs.append(
                    {
                        "name": name[len("refs/heads/"):],
                        "sha": ((r.get("object") or {}).get("sha") or ""),
                    }
                )
        return refs

    def _assert_revision(self, full: str, ref: str, token: str, expected: str = "") -> str:
        refs = self._line_refs(full, token)
        found = next((entry for entry in refs if entry["name"] == ref), None)
        if found is None or not found["sha"]:
            raise Conflict("the delivery scratch ref changed")
        if expected and found["sha"] != expected:
            raise Conflict("the delivery scratch head changed")
        return found["sha"]

    def _commit_revision(self, full: str, ref: str, parent: str, contents: dict[str, str], message: str, token: str) -> None:
        self._assert_revision(full, ref, token, parent)
        base = self._req("GET", f"/repos/{full}/git/commits/{parent}", token)
        tree = self._req("POST", f"/repos/{full}/git/trees", token, {
            "base_tree": base["tree"]["sha"],
            "tree": [{"path": path, "mode": "100644", "type": "blob", "content": text} for path, text in sorted(contents.items())],
        })
        commit = self._req("POST", f"/repos/{full}/git/commits", token, {"message": message, "tree": tree["sha"], "parents": [parent]})
        try:
            self._req("PATCH", f"/repos/{full}/git/refs/heads/{ref}", token, {"sha": commit["sha"], "force": False})
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422):
                raise Conflict("the delivery scratch head changed before commit") from exc
            raise

    def _require_line_ref(self, full: str, token: str) -> str:
        """The line's one scratch ref, or a loud, distinct refusal. A silently-empty
        resolution would read as an empty scratch and hand every downstream act a
        misleading refusal (a Sign would surface the stamper's journal-absent message
        for a line whose journal is right there on its ref), so an unresolvable ref is
        its own error, named as such."""
        refs = self._line_refs(full, token)
        if not refs:
            raise ValueError(
                f"{full} carries no delivery/* scratch ref: not an open delivery line"
            )
        if len(refs) > 1:
            names = ", ".join(sorted(r["name"] for r in refs))
            raise ValueError(
                f"{full} carries more than one delivery/* scratch ref ({names}); "
                "exactly one may exist - refusing to pick"
            )
        return refs[0]["name"]

    def _require_token(self) -> str:
        token = self._token_provider() or ""
        if not token:
            raise RuntimeError("no git credential configured; set it in the Console settings")
        return token

    def _req(self, method: str, path: str, token: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{_API}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        with self._transport.request(req, timeout=20) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else {}

    def _holds(self, name: str, token: str) -> bool:
        """Read whether this exact repository address is held.

        Only confirmed 404 means absence. A successful response must identify the
        requested full_name; a rename redirect to a different address leaves this
        name available."""
        full = f"{self._org}/{name}"
        try:
            repo = self._req("GET", f"/repos/{full}", token)
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise SourceUnavailable("repository evidence could not be read") from exc
        # Require the requested repository address after following any rename redirect.
        if not isinstance(repo, dict) or not isinstance(repo.get("full_name"), str) or not repo["full_name"]:
            raise SourceUnavailable("repository identity response is malformed")
        return repo["full_name"].lower() == full.lower()

    def _create_repo(self, name: str, token: str) -> None:
        if self._holds(name, token):
            return  # already exists under this exact name
        try:
            self._req(
                "POST", f"/orgs/{self._org}/repos", token,
                {"name": name, "private": True, "auto_init": True},
            )
        except SourceUnavailable:
            raise
        except (urllib.error.HTTPError, ValueError, TypeError) as exc:
            raise RuntimeError(f"could not create {self._org}/{name}: {exc}") from exc

    def _exists(self, full: str, path: str, token: str, ref: str = "") -> bool:
        try:
            suffix = f"?ref={quote(ref, safe='')}" if ref else ""
            self._req("GET", f"/repos/{full}/contents/{path}{suffix}", token)
            return True
        except SourceUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise SourceUnavailable("repository evidence could not be read") from exc

    def _put_file(
        self, full: str, path: str, content: str, message: str, token: str, branch: str = ""
    ) -> None:
        body: dict = {"message": message, "content": base64.b64encode(content.encode()).decode()}
        if branch:
            body["branch"] = branch
        self._req("PUT", f"/repos/{full}/contents/{path}", token, body)
