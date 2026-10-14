"""The scope substance itemizes estimatekit's own TSV/PUML data east-west (the project-files
REST door the MCP read_project_file mirrors): the requirement spine, the phase decomposition,
the assumptions, and the architecture (guidelines, per-phase components, and each phase's .puml
diagram source). It is additive over summary+audit and self-degrading - a studio hiccup drops
only the affected section, never the pane. Audit: csd-intent ."""

from pytest_intent import intent

from orchestrator.adapters.outbound.studios.http_studio_gateway import HttpStudioGateway
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


def _tsv(header: list[str], *rows: list[str]) -> str:
    return "\n".join("\t".join(r) for r in (header, *rows)) + "\n"


BRD = _tsv(
    ["Category", "Req ID", "Description", "Original Text", "Lines"],
    ["Filtering", "FILT-001", "Add a filter", "orig", "4-5"],
    ["Filtering", "FILT-002", "Draw POIs", "orig", "27"],
    ["Data", "DATA-001", "Export CSV", "orig", "9"],  # deliberately absent from the matrix
)
PHASES = _tsv(
    ["Phase", "Phase ID", "Name", "Description", "Integration Type", "Examples"],
    ["Phase 1", "P1", "Priority", "Quick wins", "Existing", "ex"],
    ["Phase 2", "P2", "Backlog", "Core work", "Existing", "ex"],
)
MATRIX = _tsv(
    ["Category", "Req ID", "Description", "Phase 1", "Phase 2", "Notes"],
    ["Filtering", "FILT-001", "Add a filter", "✓", "", ""],
    ["Filtering", "FILT-002", "Draw POIs", "", "✓", ""],
)
ASSUMPTIONS = _tsv(
    ["Group", "Assumption ID", "Assumption", "Short Title", "Confidence", "Impact", "Req IDs"],
    ["Team", "A-001", "Team knows the platform", "Team knows", "HIGH", "CRITICAL", "ALL"],
    ["Pricing", "A-002", "A margin covers it", "Margin", "LOW", "HIGH", "FILT-002"],
)
GUIDELINES = _tsv(
    ["Group", "Guideline ID", "Guideline", "Description", "Rationale"],
    ["Positioning", "GUIDE-001", "Channel Not Core", "A channel over core IT", "avoids scope creep"],
)
COMPONENTS = _tsv(
    ["Layer", "Component", "Technology", "Description", "Phase 1 Scope"],
    ["Frontend", "Web App", "React", "SPA", "Full"],
    ["Data", "Database", "Postgres", "Store", "Full"],
)
PUML = "@startuml\ntitle Phase 1\n[Web App] --> [Database]\n@enduml\n"

FILES = {
    "files": [
        {"path": "data/requirements/01-brd.tsv", "name": "01-brd.tsv", "kind": "tsv", "directory": "data/requirements"},
        {"path": "data/architecture/00-guidelines.tsv", "name": "00-guidelines.tsv", "kind": "tsv", "directory": "data/architecture"},
        {"path": "data/architecture/P1-components.tsv", "name": "P1-components.tsv", "kind": "tsv", "directory": "data/architecture"},
        {"path": "data/architecture/P1-overview.puml", "name": "P1-overview.puml", "kind": "puml", "directory": "data/architecture"},
    ]
}
DATA = {
    "data/requirements/01-brd.tsv": BRD,
    "data/requirements/02-phases.tsv": PHASES,
    "data/requirements/03-matrix.tsv": MATRIX,
    "data/assumptions/02-assumptions.tsv": ASSUMPTIONS,
    "data/architecture/00-guidelines.tsv": GUIDELINES,
    "data/architecture/P1-components.tsv": COMPONENTS,
    "data/architecture/P1-overview.puml": PUML,
}


def _gateway(rest):
    gw = HttpStudioGateway(config=None)
    gw._rest = rest  # override the one HTTP seam; everything else is pure shaping
    return gw


def _full_rest(_studio, path, method="GET"):
    if path.endswith("/summary"):
        return {"name": "Acme", "client": "Acme Co", "description": "Do the thing",
                "phase_count": 2, "requirement_count": 3, "assumption_count": 2}
    if path.endswith("/audit"):
        return {"passed": True, "passed_count": 10, "failed_count": 0, "suggestions": []}
    if path.endswith("/files"):
        return FILES
    if "/files/" in path:
        rel = path.split("/files/", 1)[1]
        if rel not in DATA:
            raise SourceUnavailable("404")
        return {"path": rel, "content": DATA[rel]}
    raise SourceUnavailable("optional rendering unavailable")


@intent("INT-FC-R56")
def test_scope_substance_itemizes_requirements_phases_assumptions_and_architecture():
    out = _gateway(_full_rest).scope_substance("acme", studio="estimatekit")

    # summary + audit still head the substance
    assert out["summary"]["requirement_count"] == 3
    assert out["audit"]["passed"] is True

    # the requirement spine, phase-annotated from the matrix (DATA-001 has no allocation)
    reqs = {r["id"]: r for r in out["requirements"]}
    assert reqs["FILT-001"]["phases"] == ["P1"]
    assert reqs["FILT-002"]["phases"] == ["P2"]
    assert reqs["DATA-001"]["phases"] == []
    assert reqs["FILT-001"]["category"] == "Filtering"

    # the phase decomposition is the inverse: which requirements fall in which phase
    phases = {p["id"]: p for p in out["phases"]}
    assert phases["P1"]["name"] == "Priority"
    assert phases["P1"]["requirement_ids"] == ["FILT-001"]
    assert phases["P2"]["requirement_ids"] == ["FILT-002"]

    # the assumptions register, with confidence/impact and the requirements each bears on
    assumptions = {a["id"]: a for a in out["assumptions"]}
    assert assumptions["A-001"]["impact"] == "CRITICAL"
    assert assumptions["A-002"]["req_ids"] == ["FILT-002"]

    # the architecture: guidelines, per-phase components (scope captured), diagram SOURCE
    arch = out["architecture"]
    assert arch["guidelines"][0]["name"] == "Channel Not Core"
    assert {c["component"] for c in arch["components"]} == {"Web App", "Database"}
    assert all(c["phase"] == "P1" for c in arch["components"])
    assert arch["components"][0]["scope"] == "Full"
    assert arch["diagrams"][0] == {"name": "P1-overview", "phase": "P1", "puml": PUML}


@intent("INT-FC-R56")
def test_scope_substance_degrades_without_severing_the_pane():
    # estimatekit unreachable at the summary -> {} (the pane falls back to the record)
    def down(_s, _p, method="GET"):
        raise SourceUnavailable("unreachable")

    assert _gateway(down).scope_substance("acme", studio="estimatekit") == {}

    # summary + audit answer but the data files do not: the counts still render, and every
    # itemized section is simply absent rather than raising into the page.
    def partial(_s, path, method="GET"):
        if path.endswith("/summary"):
            return {"name": "Acme", "requirement_count": 0}
        if path.endswith("/audit"):
            return {"passed": False, "passed_count": 0, "failed_count": 1, "suggestions": []}
        raise SourceUnavailable("files door down")

    out = _gateway(partial).scope_substance("acme", studio="estimatekit")
    assert out["summary"]["name"] == "Acme"
    assert out["audit"]["passed"] is False
    assert not any(k in out for k in ("requirements", "phases", "assumptions", "architecture"))
