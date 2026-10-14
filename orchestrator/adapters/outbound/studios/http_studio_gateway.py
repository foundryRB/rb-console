"""HttpStudioGateway: the Console's two server-to-server doors into the studios.

The Console's own calls ride each studio's REST /api over the in-cluster ``internal``
Service port (east-west, past the OIDC sidecar): app-to-app substance is RPC with typed
statuses, not tool-calling. The MCP door (/mcp, per-door Basic auth from the stored
fc-mcp-<studio> credential) is the agents' door; the gateway uses it for health probes
and for catalog and artifact queries. MCP
queries hit the studio's in-cluster Service directly with the public host in the Host
header (to satisfy the MCP transport's DNS-rebinding guard). Every read degrades
gracefully: a studio that is down or a bad credential yields reachable=False /
exists=None rather than raising, because the cockpit must render even when a studio
is offline.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import ClassVar

from orchestrator.adapters.outbound.studios.platform_app import platform_app
from orchestrator.domain.catalog import parse_catalog_agent
from orchestrator.domain.delivery import studio_project_key
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.exceptions.studio_tool_error import StudioToolError
from orchestrator.domain.model.app_lifecycle_result import AppLifecycleResult
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.model.platform_app import PlatformApp
from orchestrator.domain.model.studio_artifact import StudioArtifact
from orchestrator.domain.model.studio_health import StudioHealth

_log = logging.getLogger(__name__)
_SOURCE_ERRORS = (SourceUnavailable, StudioToolError, urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError)

_PROTO = "2025-06-18"

#: In-cluster Service ports for the east-west ``internal`` door, which targets the app
#: container directly (past the OIDC sidecar). The public host is a BROWSER door: a
#: server-to-server request to it gets the login page, not the API.
INTERNAL_PORTS: ClassVar[dict[str, int]] = {"estimatekit": 8001, "protopane": 8801, "platform-studio": 8001}


def internal_base_url(studio: str, svc_domain: str = "") -> str:
    """One studio's east-west base URL. The single definition of where a studio answers
    app-to-app, so every console-side caller reaches the same door: the gateway's own
    reads, and the gate stamper's export (which is handed this URL rather than left to
    guess an instance from the environment)."""
    svc = svc_domain or os.environ.get("FC_STUDIO_SVC_DOMAIN", "svc.cluster.local")
    return f"http://{studio}.{studio}.{svc}:{INTERNAL_PORTS[studio]}"


def _norm(slug: str) -> str:
    """Lowercased, alphanumerics only: robust to the separator and case drift between a
    lowercased registry name and a repository that keeps its own casing."""
    return re.sub(r"[^a-z0-9]", "", slug.lower())


class HttpStudioGateway:
    #: The connected studios. estimatekit/protopane/platform-studio carry per-delivery
    #: artifacts; playbook-studio is the always-on skill source (health only here).
    _STUDIOS = ("estimatekit", "protopane", "platform-studio", "playbook-studio")
    #: In-cluster Service ports (protopane differs); the default is 8000.
    _PORTS: ClassVar[dict[str, int]] = {"protopane": 8800}
    #: The repository scaffold is a write the studio performs in the request (refresh its
    #: platform checkout, create the repository, seed main, open the deploy branch), about
    #: ten seconds of GitHub calls; the read timeout cut it off partway. Kept inside the
    #: execution door's 75-second proxy limit, with room for the rest of the establish.
    _SCAFFOLD_TIMEOUT = 60

    def __init__(self, config, domain: str | None = None, timeout: int = 8) -> None:
        self._config = config
        # No fallback: a default (one ground's host) would query a second install's cockpit
        # against the first install's studios (anti-pattern 19). Unset, queries degrade to
        # unreachable rather than silently hitting the wrong ground.
        self._domain = domain or os.environ.get("FC_DOMAIN", "")
        # In-cluster Service DNS for server-to-server queries; overridable for dev/test.
        self._svc = os.environ.get("FC_STUDIO_SVC_DOMAIN", "svc.cluster.local")
        self._timeout = timeout
        self._proto_canvas_cache: dict = {}
        self._proto_canvas_studio: str = ''

    def _port(self, studio: str) -> int:
        return self._PORTS.get(studio, 8000)

    def _query_url(self, studio: str) -> str:
        return f"http://{studio}.{studio}.{self._svc}:{self._port(studio)}/mcp/"

    def _host(self, studio: str) -> str:
        # The MCP transport's allowed-hosts guard expects the public hostname.
        return f"{studio}.{self._domain}"

    def _link(self, studio: str) -> str:
        # User-facing deep links go to the public host (through the OIDC proxy).
        return f"https://{studio}.{self._domain}"

    def _auth_header(self, studio: str) -> str | None:
        user = (self._config.get_setting(f"mcp-{studio}") or {}).get("user", "")
        pw = self._config.get_secret(f"mcp-{studio}")
        if not (user or pw):
            return None
        return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()

    def _post(self, studio: str, payload: dict, session: str | None = None):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Host": self._host(studio),
            "MCP-Protocol-Version": _PROTO,
        }
        auth = self._auth_header(studio)
        if auth:
            headers["Authorization"] = auth
        if session:
            headers["Mcp-Session-Id"] = session
        req = urllib.request.Request(
            self._query_url(studio), data=json.dumps(payload).encode(), method="POST", headers=headers
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.headers.get("Mcp-Session-Id"), resp.read()

    @staticmethod
    def _sse(raw: bytes) -> dict:
        """Pull the JSON-RPC envelope out of an SSE response (event: message / data: {...})."""
        body = raw.decode("utf-8", "replace")
        data = next((line[5:].strip() for line in body.splitlines() if line.startswith("data:")), body)
        try:
            envelope = json.loads(data)
        except json.JSONDecodeError as exc:
            raise SourceUnavailable("Studio response is malformed") from exc
        if not isinstance(envelope, dict):
            raise SourceUnavailable("Studio response is malformed")
        return envelope

    def _initialize(self, studio: str) -> str | None:
        session, _ = self._post(
            studio,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": _PROTO,
                    "capabilities": {},
                    "clientInfo": {"name": "foundry-console", "version": "0"},
                },
            },
        )
        try:
            self._post(studio, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 405):
                raise
            _log.debug("Studio initialization notification unsupported")
        return session

    def _tool(self, studio: str, tool: str, args: dict | None = None):
        """Call one MCP tool and return its parsed return value (the tool's own JSON).

        Raises StudioToolError when the studio refuses. MCP reports a refusal two
        ways -- a JSON-RPC ``error`` envelope, or a result carrying ``isError`` --
        and a read that inspects neither lets a refused call fall through
        ``.get("result", {})`` as an empty list: every caller then sees "the studio
        answered, with nothing", indistinguishable from a legitimately empty read
        (create_app_repo failing to seed a new repo reaches establish as ``{}``),
        and no try/except upstream can catch what never raises. A refusal must be
        loud here or it cannot be handled anywhere.
        """
        session = self._initialize(studio)
        _, raw = self._post(
            studio,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args or {}}},
            session,
        )
        envelope = self._sse(raw)
        if isinstance(envelope.get("error"), dict):
            raise self._mcp_error(studio, tool, str(envelope["error"].get("message", "")))
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise SourceUnavailable("Studio tool response is malformed")
        if result.get("isError"):
            texts = [
                item.get("text", "")
                for item in result.get("content", []) or []
                if item.get("type") == "text"
            ]
            raise self._mcp_error(studio, tool, " ".join(t for t in texts if t))
        # Prefer MCP structuredContent. FastMCP wraps a non-dict return (e.g. a list) as
        # {"result": <value>}; a dict return (e.g. estimatekit {"projects": [...]}) arrives
        # as-is. Fall back to the text content blocks, which a list-returning tool emits
        # one per item, so collect them all rather than only the first.
        sc = result.get("structuredContent")
        if isinstance(sc, dict) and list(sc.keys()) == ["result"]:
            return sc["result"]
        if sc is not None:
            return sc
        parsed = []
        for item in result.get("content", []) or []:
            if item.get("type") == "text":
                try:
                    parsed.append(json.loads(item["text"]))
                except json.JSONDecodeError:
                    parsed.append(item["text"])
        return parsed[0] if len(parsed) == 1 else parsed

    @staticmethod
    def _mcp_error(studio: str, tool: str, detail: str) -> StudioToolError:
        return StudioToolError(studio, tool, detail.removeprefix(f"Error executing tool {tool}: "))

    def tool_url(self, studio: str) -> str:
        return internal_base_url(studio, self._svc) if studio in INTERNAL_PORTS else ""

    def health(self) -> list[StudioHealth]:
        out: list[StudioHealth] = []
        for studio in self._STUDIOS:
            try:
                self._initialize(studio)
                out.append(StudioHealth(studio, True, "reachable", self._link(studio)))
            except _SOURCE_ERRORS:
                out.append(StudioHealth(studio, False, "unreachable", self._link(studio)))
        return out

    def agent_catalog(self) -> list[CatalogAgent]:
        """The playbook's agent roster over the studio's MCP door (``list_agents``): the same
        door, with the same stored credential, the workers pull their skills through. One call
        for the whole roster. Degrades to [] when the studio is down or refuses - the service
        logs the degradation; a run is never refused for want of a catalog."""
        try:
            data = self._tool("playbook-studio", "list_agents")
        except _SOURCE_ERRORS:  # unreachable or refused: no catalog, not a failed run
            return []
        rows = data if isinstance(data, list) else []
        return [a for a in (parse_catalog_agent(r) for r in rows) if a is not None]

    def platform_apps(self) -> list[PlatformApp]:
        """Normalize the available platform application inventory for Fleet and Studios."""
        try:
            data = self._rest("platform-studio", "/api/apps")
        except _SOURCE_ERRORS as exc:
            raise SourceUnavailable("Platform application inventory unavailable") from exc
        if not isinstance(data, list):
            raise SourceUnavailable("platform application inventory is malformed")
        return [platform_app(row) for row in data]

    def playbook_repo(self) -> str:
        """The playbook's ``owner/name``, over playbook-studio's ``get_sync_status``.

        The studio owns the working clone it pushes, so its upstream is the playbook's
        identity by construction: it cannot be stale about the repo it is cloned from,
        which a literal here could be after a rename or an org move. Same door and same
        stored credential the workers already pull their skills through.

        Degrades to "" on every failure mode, and they are all the same answer -
        UNKNOWN. The studio may be down, may refuse, or may be an operator-owned local
        composition managing no clone at all, in which case `get_sync_status` is not
        even registered as a tool. None of those is evidence about which repo the
        playbook is, so the caller leaves the row unmarked rather than guessing one."""
        try:
            data = self._tool("playbook-studio", "get_sync_status")
        except _SOURCE_ERRORS:  # down, refused, or no such tool: unknown, never a guess
            return ""
        return str((data or {}).get("repo") or "").strip() if isinstance(data, dict) else ""

    def create_app_repo(
        self, name: str, display_name: str, description: str, repo: str = ""
    ) -> None:
        """Create a templated app repo via platform-studio (the walking-skeleton
        scaffold: the REF-AppContract contract rendered, deploy branch included).

        Raises StudioToolError on a refusal (the repo already exists, no fleet
        write credential, the scaffold could not land) and the underlying
        SourceUnavailable when the studio is unreachable, so establish can tell
        the two apart: one is a reason, the other is a degraded platform."""
        self._rest(
            "platform-studio",
            "/api/repos/app",
            method="POST",
            payload={
                "name": name,
                "display_name": display_name,
                "description": description,
                # The repository to create it in, a fact of its own: empty means the
                # studio defaults it to the app name, which is right only where an
                # organisation names its repositories for the apps they hold.
                "repo": repo,
            },
            timeout=self._SCAFFOLD_TIMEOUT,
        )

    def pause_app(self, name: str) -> AppLifecycleResult:
        """Scale an app to zero via platform-studio (a direct-commit lifecycle toggle, not
        a gated PR). Returns the app with its new paused status."""
        data = self._rest(
            "platform-studio", f"/api/apps/{name}/pause", method="POST"
        )
        if not isinstance(data, dict) or data.get("name") != name:
            raise SourceUnavailable("application lifecycle acknowledgement is malformed")
        if "paused" in data and data["paused"] is not True:
            raise SourceUnavailable("application lifecycle acknowledgement is malformed")
        status = data.get("status")
        if status is not None and not isinstance(status, str):
            raise SourceUnavailable("application lifecycle acknowledgement is malformed")
        return AppLifecycleResult(name, True, status)

    def resume_app(self, name: str) -> AppLifecycleResult:
        """Resume a paused app via platform-studio. Returns the app with its running status."""
        data = self._rest(
            "platform-studio", f"/api/apps/{name}/resume", method="POST"
        )
        if not isinstance(data, dict) or data.get("name") != name:
            raise SourceUnavailable("application lifecycle acknowledgement is malformed")
        if "paused" in data and data["paused"] is not False:
            raise SourceUnavailable("application lifecycle acknowledgement is malformed")
        status = data.get("status")
        if status is not None and not isinstance(status, str):
            raise SourceUnavailable("application lifecycle acknowledgement is malformed")
        return AppLifecycleResult(name, False, status)

    def estimatekit_slugs(self) -> set[str]:
        """Every estimatekit project slug (one call), for the Fleet to match by slug."""
        try:
            data = self._tool("estimatekit", "list_projects")
        except _SOURCE_ERRORS as exc:
            raise SourceUnavailable("Estimation project inventory unavailable") from exc
        projects = data.get("projects") if isinstance(data, dict) else None
        if not isinstance(projects, list) or any(not isinstance(slug, str) or not slug for slug in projects):
            raise SourceUnavailable("Estimation project inventory is malformed")
        return set(projects)

    def protopane_slugs(self) -> set[str]:
        """Every protopane prototype slug (one call), for the Fleet to match by slug."""
        return {project["slug"] for project in self._prototype_projects()}

    def _prototype_projects(self) -> list[dict]:
        """Validate project identities before either fleet or artifact projection."""
        try:
            data = self._tool("protopane", "list_projects")
        except _SOURCE_ERRORS as exc:
            raise SourceUnavailable("Prototype inventory unavailable") from exc
        if not isinstance(data, list) or any(not isinstance(project, dict) or not isinstance(project.get("slug"), str) or not project["slug"] for project in data):
            raise SourceUnavailable("Prototype inventory is malformed")
        return data

    # --- the east-west REST door -------------------------------------------------
    # MCP is the agents' door; the Console's own calls are app-to-app, so they ride
    # plain REST: each studio's /api over the `internal` Service port, which targets
    # the app container directly (past the OIDC sidecar). In-cluster only - the
    # Gateway never routes that port - so no human OIDC and no agent Basic applies
    # here. A non-2xx answer is a typed refusal: the studios map domain errors to
    # statuses with the exception class in the body ({"error": ClassName}), so the
    # StudioToolError raised here carries the name as data, no phrase-matching.
    def _rest(self, studio: str, path: str, method: str = "GET", payload: dict | None = None,
              timeout: float | None = None):
        url = internal_base_url(studio, self._svc) + path
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {}
            name = str(body.get("error", "")) if isinstance(body, dict) else ""
            detail = str(body.get("detail", "")) if isinstance(body, dict) else ""
            raise StudioToolError(
                studio, f"{method} {path}", detail or raw or str(exc), error_name=name
            ) from exc

        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            raise SourceUnavailable("Studio REST response unavailable") from exc

    def _rest_files(self, studio: str, slug: str) -> list[dict]:
        """The studio's editable data-file listing (path/name/kind/directory), the same read
        the MCP list_project_files tool mirrors. Lets the reader discover files whose names
        vary (the per-phase .puml diagrams) instead of guessing them."""
        data = self._rest(studio, f"/api/projects/{slug}/files")
        files = data.get("files", []) if isinstance(data, dict) else []
        return [f for f in files if isinstance(f, dict)]

    def _rest_file(self, studio: str, slug: str, path: str) -> str:
        """One data file's raw text ('' when absent or unreadable), the read the MCP
        read_project_file tool mirrors. Swallows its own errors so a missing file drops only
        the section that wanted it, never the pane."""
        try:
            data = self._rest(studio, f"/api/projects/{slug}/files/{path}")
        except _SOURCE_ERRORS:  # an absent file must not fail the pane
            return ""
        return data.get("content", "") if isinstance(data, dict) else ""

    @staticmethod
    def _tsv_rows(text: str) -> list[dict]:
        """Parse tab-separated text into header-keyed row dicts. estimatekit's data files are
        TSV with a byte-stable header row; blank lines and empty rows are skipped."""
        lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
        if len(lines) < 2:
            return []
        headers = [h.strip() for h in lines[0].split("\t")]
        rows: list[dict] = []
        for line in lines[1:]:
            cells = line.split("\t")
            rows.append({h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(headers)})
        return rows

    def scope_substance(self, slug: str, *, studio: str) -> dict:
        """The scope phase's substance, itemized from estimatekit's own REST API east-west:
        the project identity + counts and the audit verdict, PLUS the content an operator
        reads at a glance - the requirement spine (id/category/description/phase), the phase
        decomposition, the assumptions, and the architecture (guidelines, per-phase
        components, and the per-phase diagram source). The Console renders this natively; the
        committed proposal.md is a last-resort fallback, not the substance. {} only when
        estimatekit is unreachable or holds no project for the slug."""
        try:
            summary = self._rest(studio, f"/api/projects/{slug}/summary")
        except _SOURCE_ERRORS:  # a read must not fail the pane
            return {}
        out: dict = {"summary": summary if isinstance(summary, dict) else {}}
        try:
            audit = self._rest(studio, f"/api/projects/{slug}/audit", method="POST")
        except _SOURCE_ERRORS:  # the summary + items still render without the audit
            audit = None
        if isinstance(audit, dict):
            out["audit"] = {
                "passed": bool(audit.get("passed")),
                "passed_count": audit.get("passed_count", 0),
                "failed_count": audit.get("failed_count", 0),
                "suggestions": [
                    {
                        "title": s.get("title", ""),
                        "detail": s.get("detail", ""),
                        "severity": s.get("severity", ""),
                        "category": s.get("category", ""),
                    }
                    for s in (audit.get("suggestions") or [])
                ][:12],
            }
        # The itemized reads sit on top of summary+audit and are purely additive: a studio
        # hiccup mid-read drops the items but keeps whatever already rendered.
        try:
            out.update(self._scope_items(slug, studio=studio))
        except _SOURCE_ERRORS:  # itemization never fails the pane
            _log.debug("Optional studio response unavailable")
        return out

    def _scope_items(self, slug: str, *, studio: str) -> dict:
        """Itemize estimatekit's scope TSV data east-west: the requirement spine, the phase
        decomposition (which requirements fall in which phase, from the matrix), the
        assumptions, and the architecture. Each section is best-effort - a missing or
        unreadable file drops only that section."""
        out: dict = {}

        # Phases (02-phases.tsv): the "Phase 1" column label maps to the "P1" phase id.
        phases = [
            {
                "id": r.get("Phase ID", ""),
                "phase": r.get("Phase", ""),
                "name": r.get("Name", ""),
                "description": r.get("Description", ""),
                "requirement_ids": [],
            }
            for r in self._tsv_rows(self._rest_file(studio, slug, "data/requirements/02-phases.tsv"))
            if r.get("Phase ID", "")
        ]
        name_to_id = {p["phase"]: p["id"] for p in phases if p["phase"]}

        # Matrix (03-matrix.tsv): a ticked phase column allocates the Req ID to that phase.
        alloc: dict[str, list[str]] = {}
        for r in self._tsv_rows(self._rest_file(studio, slug, "data/requirements/03-matrix.tsv")):
            rid = r.get("Req ID", "")
            if rid:
                hits = [pid for pname, pid in name_to_id.items() if r.get(pname, "")]
                if hits:
                    alloc[rid] = hits

        # Requirements (01-brd.tsv): the id / category / description spine, phase-annotated.
        requirements = []
        for r in self._tsv_rows(self._rest_file(studio, slug, "data/requirements/01-brd.tsv")):
            rid = r.get("Req ID", "")
            if not rid:
                continue
            requirements.append(
                {
                    "id": rid,
                    "category": r.get("Category", ""),
                    "description": r.get("Description", ""),
                    "phases": alloc.get(rid, []),
                }
            )
        # Invert the allocation into the phase decomposition.
        by_id = {p["id"]: p for p in phases}
        for req in requirements:
            for pid in req["phases"]:
                if pid in by_id:
                    by_id[pid]["requirement_ids"].append(req["id"])

        if requirements:
            out["requirements"] = requirements[:500]
        if phases:
            out["phases"] = phases

        # Assumptions (02-assumptions.tsv): the register, with confidence/impact and refs.
        assumptions = []
        for r in self._tsv_rows(self._rest_file(studio, slug, "data/assumptions/02-assumptions.tsv")):
            aid, text = r.get("Assumption ID", ""), r.get("Assumption", "")
            if not (aid or text):
                continue
            assumptions.append(
                {
                    "id": aid,
                    "group": r.get("Group", ""),
                    "title": r.get("Short Title", ""),
                    "assumption": text,
                    "confidence": r.get("Confidence", ""),
                    "impact": r.get("Impact", ""),
                    "req_ids": [p.strip() for p in r.get("Req IDs", "").split(",") if p.strip()],
                }
            )
        if assumptions:
            out["assumptions"] = assumptions[:200]

        activities, phase_effort = self._activities(slug, studio=studio)
        if activities:
            out["activities"] = activities[:500]
            out["estimate"] = {
                "phases": [
                    {"id": pid, "effort_md": round(v, 1)} for pid, v in sorted(phase_effort.items())
                ],
                "total_md": round(sum(phase_effort.values()), 1),
            }

        architecture = self._architecture(slug, studio=studio)
        if architecture:
            out["architecture"] = architecture
        return out

    def _activities(self, slug: str, *, studio: str) -> tuple[list[dict], dict[str, float]]:
        """The activity breakdown under data/activities/ (P{n}-{group}.tsv): each activity
        with its effort in man-days, plus the per-phase effort sums. The sums are the same
        numbers estimatekit's own workbooks total - itemized here so the operator reads the
        estimate at the gate without opening a workbook."""
        try:
            files = [
                f for f in self._rest_files(studio, slug)
                if f.get("directory") == "data/activities"
            ]
        except _SOURCE_ERRORS:  # the estimate is additive; its absence drops only itself
            return [], {}
        activities: list[dict] = []
        phase_effort: dict[str, float] = {}
        for f in sorted(files, key=lambda x: x.get("name", "")):
            name = f.get("name", "")
            phase = name.split("-", 1)[0] if "-" in name else ""
            for r in self._tsv_rows(self._rest_file(studio, slug, f.get("path", ""))):
                aid, act = r.get("Activity ID", ""), r.get("Activity", "")
                if not (aid or act):
                    continue
                try:
                    effort = float(r.get("Effort (MD)", "") or 0)
                except ValueError:
                    effort = 0.0
                activities.append(
                    {
                        "id": aid,
                        "phase": phase,
                        "group": r.get("Group", ""),
                        "activity": act,
                        "effort_md": effort,
                        "req_ids": [p.strip() for p in r.get("Req IDs", "").split(",") if p.strip()],
                        "description": r.get("Description", ""),
                    }
                )
                phase_effort[phase] = phase_effort.get(phase, 0.0) + effort
        return activities, phase_effort

    def _architecture(self, slug: str, *, studio: str) -> dict:
        """The scope architecture, under estimatekit's data/architecture/: the guidelines and
        per-phase component inventory (both TSV), plus each phase's diagram SOURCE (.puml).
        The .puml is the diagram artifact itself, surfaced as source and rendered natively -
        NOT round-tripped through a third-party PlantUML server, which would ship a client's
        architecture off-cluster (estimatekit does not rasterise it either; its own slides
        summarise the components + guidelines). Filenames vary, so enumerate the listing."""
        try:
            arch = [f for f in self._rest_files(studio, slug) if f.get("directory") == "data/architecture"]
        except _SOURCE_ERRORS:  # the listing is best-effort like every other read
            return {}
        if not arch:
            return {}
        out: dict = {}

        gpath = next((f["path"] for f in arch if f.get("name") == "00-guidelines.tsv"), None)
        guidelines = []
        if gpath:
            for r in self._tsv_rows(self._rest_file(studio, slug, gpath)):
                gid = r.get("ID") or r.get("Guideline ID", "")
                name = r.get("Guideline") or r.get("Name", "")
                if not (gid or name):
                    continue
                guidelines.append(
                    {
                        "id": gid,
                        "group": r.get("Group", ""),
                        "name": name,
                        "description": r.get("Description", ""),
                        "rationale": r.get("Rationale", ""),
                    }
                )
        if guidelines:
            out["guidelines"] = guidelines[:100]

        components = []
        for f in sorted(arch, key=lambda x: x.get("name", "")):
            name = f.get("name", "")
            if not name.endswith("-components.tsv"):
                continue
            phase = name[: -len("-components.tsv")]  # "P1-components.tsv" -> "P1"
            for r in self._tsv_rows(self._rest_file(studio, slug, f["path"])):
                comp = r.get("Component") or r.get("Name", "")
                if not comp:
                    continue
                scope = next((v for k, v in r.items() if k.endswith("Scope")), "")
                components.append(
                    {
                        "phase": phase,
                        "layer": r.get("Layer", ""),
                        "component": comp,
                        "technology": r.get("Technology", ""),
                        "description": r.get("Description", ""),
                        "scope": scope,
                    }
                )
        if components:
            out["components"] = components[:300]

        diagrams = []
        for f in sorted(arch, key=lambda x: x.get("name", "")):
            if f.get("kind") != "puml" and not f.get("name", "").endswith(".puml"):
                continue
            puml = self._rest_file(studio, slug, f["path"])
            if not puml.strip():
                continue
            stem = f.get("name", "").rsplit(".", 1)[0]  # "P1-overview"
            entry = {"name": stem, "phase": stem.split("-", 1)[0], "puml": puml}
            # The studio supplies its rendered diagram beside the canonical source.
            try:
                rendered = self._rest(
                    studio,
                    f"/api/projects/{slug}/architecture/diagrams/{f.get('name', '')}",
                )
                svg = rendered.get("svg", "") if isinstance(rendered, dict) else ""
                if svg.lstrip().startswith("<svg") or "<svg" in svg[:500]:
                    entry["svg"] = svg
            except _SOURCE_ERRORS:  # diagram source remains available without a render
                _log.debug("Optional studio response unavailable")
            diagrams.append(entry)
            if len(diagrams) >= 12:
                break
        if diagrams:
            out["diagrams"] = diagrams
        return out


    def _protopane_canvas(self, studio: str) -> dict:
        """Cache the selected studio's Tailwind Play runtime, token config and stylesheet.

        The runtime styles screen utility markup with the studio's canvas recipe.
        """
        if self._proto_canvas_cache and self._proto_canvas_studio == studio:
            return self._proto_canvas_cache
        out = {"canvas_js": "", "canvas_css": ""}
        try:
            base = internal_base_url(studio, self._svc)

            def fetch(path: str) -> str:
                with urllib.request.urlopen(base + path, timeout=self._timeout) as r:
                    return r.read().decode("utf-8", "replace")

            # Order matters: the runtime first, then the config that parameterizes it.
            out["canvas_js"] = fetch("/vendor/tailwind-play.js") + "\n;\n" + fetch("/canvas/tw-config.js")
            out["canvas_css"] = fetch("/canvas/theme.css")
        except _SOURCE_ERRORS:  # the pane degrades to tokens-only rather than fail
            _log.debug("Optional studio response unavailable")
        if all(out.values()):
            self._proto_canvas_cache.clear()
            self._proto_canvas_cache.update(out)
            self._proto_canvas_studio = studio
        return out

    def design_substance(self, slug: str, *, studio: str) -> dict:
        """The design phase's substance: the protopane prototype itself, exported east-west
        (theme CSS + screen bodies), so the Console renders the real screens natively in a
        sandboxed frame - no OIDC iframe, no cookies, no cross-origin coupling."""
        slug = studio_project_key("protopane", slug)
        try:
            export = self._rest(studio, f"/api/projects/{slug}/export")
        except _SOURCE_ERRORS:  # a read must not fail the pane
            return {}
        if not isinstance(export, dict):
            return {}
        screens = [
            {
                "slug": s.get("slug", ""),
                "name": s.get("name", ""),
                "html": s.get("html", ""),
                "css": s.get("css", ""),
            }
            for s in (export.get("screens") or [])
        ]
        return {"theme_css": export.get("theme_css", ""), "screens": screens, **self._protopane_canvas(studio)}

    def artifacts_for(self, slug: str) -> dict[str, StudioArtifact]:
        return {
            "proposal": self._estimatekit(slug),
            "design": self._protopane(slug),
            "build": self._platform(slug),
        }

    def _estimatekit(self, slug: str) -> StudioArtifact:
        studio = "estimatekit"
        try:
            projects = self.estimatekit_slugs()
            exists = slug in projects
            url = f"{self._link(studio)}/projects/{slug}" if exists else self._link(studio)
            return StudioArtifact(studio, True, exists, url, "estimation project" if exists else "no project")
        except _SOURCE_ERRORS:
            return StudioArtifact(studio, False, None, self._link(studio), "unreachable")

    def _protopane(self, slug: str) -> StudioArtifact:
        studio = "protopane"
        try:
            items = self._prototype_projects()
            key = studio_project_key(studio, slug)
            match = next((p for p in items if p["slug"] == key), None)
            url = f"{self._link(studio)}/p/{key}" if match else self._link(studio)
            detail = f"{match.get('screen_count', 0)} screens" if match else "no prototype"
            return StudioArtifact(studio, True, match is not None, url, detail)
        except _SOURCE_ERRORS:
            return StudioArtifact(studio, False, None, self._link(studio), "unreachable")

    def _platform(self, slug: str) -> StudioArtifact:
        studio = "platform-studio"
        try:
            items = self.platform_apps()
            # Artifacts join on the normalized declared repository slug.
            want = _norm(slug)
            match = next((app for app in items if _norm(app.repository.rsplit("/", 1)[-1]) == want), None)
            if match is None:
                return StudioArtifact(studio, True, False, self._link(studio), "not onboarded")
            onboarded = match.onboarded
            status = match.status
            # The app's own host, as its Gateway states it - never <slug>.<domain>, which
            # composes the delivery key into a hostname the app may not serve.
            host = match.hostname
            url = f"https://{host}" if onboarded and host else self._link(studio)
            return StudioArtifact(studio, True, onboarded, url, status if onboarded else "registered, not onboarded")
        except _SOURCE_ERRORS:
            return StudioArtifact(studio, False, None, self._link(studio), "unreachable")
