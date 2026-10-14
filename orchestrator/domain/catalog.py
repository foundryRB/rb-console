"""The playbook's agent catalog, as the Console reads it: WHO runs a step.

The playbook carries one agent definition per distinct worker (REF-Universe section 4):
a name, a job title, the one-line description a harness routes on, the skills it is
licensed to run, the doors it needs bound, its posture (how freely it acts, whether it
may write, whether it is a fresh-eyes role), and the paragraph it runs under. The Console
READS that catalog over the playbook studio's door, the same door the workers pull their
skills from; it never authors an agent, and the corpus never learns the Console exists.

What the Console adds is the binding: which catalog agent each of ITS steps runs as.
That binding is the Console's own (``delivery.Phase.agent``, the maintenance acts' agents,
the promotion door's), the same way the phase->skill map is: the corpus names the people,
the Console names who it hands each step to. The catalog entry is then what the launch
reads posture and character from - and what a run row, a node, and a log name as the one
who did the work.
"""
from __future__ import annotations

from orchestrator.domain.model.catalog_agent import CatalogAgent


def parse_catalog_agent(raw: dict) -> CatalogAgent | None:
    """A catalog entry from the studio's own wire shape (the MCP ``list_agents`` /
    ``get_agent`` return: name, title, description, skills, doors, posture, body).
    None when the shape carries no name - a roster row that names nobody is not an agent."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    posture = raw.get("posture") if isinstance(raw.get("posture"), dict) else {}
    return CatalogAgent(
        name=name,
        title=str(raw.get("title") or name),
        description=str(raw.get("description") or raw.get("summary") or ""),
        skills=tuple(str(s) for s in (raw.get("skills") or [])),
        doors=tuple(str(d) for d in (raw.get("doors") or [])),
        permission=str(posture.get("permission") or ""),
        writes=bool(posture.get("writes", True)),
        fresh_eyes=bool(posture.get("fresh_eyes", False)),
        body=str(raw.get("body") or "").strip(),
    )


def agent_title(name: str) -> str:
    """A display title derived from an agent's name, for surfaces that may have no catalog
    in hand (the Settings grid, a run row while the studio is down): release-manager ->
    Release Manager. The catalog's own title wins wherever the catalog was read."""
    return " ".join(part.capitalize() for part in name.split("-") if part)
