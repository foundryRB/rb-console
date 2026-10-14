"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.domain.delivery import LEARN, SEQUENCE
from orchestrator.domain.services.maintenance_launch import ACT_AGENTS
from orchestrator.domain.services.promotion_launch import PROMOTE_AGENT


def helper_git_role_agents() -> list[tuple[str, str, str]]:
    """The catalog agents a git identity is assigned to, in line order, each with the
    steps it runs and its kind: (agent, steps, kind). The identity map is keyed on the
    AGENT, not the step (issue #62): the Builder commits as one account wherever the
    Builder works, and the Reviewer being a different agent than the Programmer is what
    lets a driven review approve a driven PR. 'console' is assignable too but is nobody in
    the catalog (it is the console's own merge/comment/close), so it rides separately.

    The Release Manager needs its own identity because the promotion door is the one act
    that commits into somewhere other than this app's default branch - a deploy branch, or
    a promote branch on a repository we do not own. Its PUSH to a pair is authorized by
    that pair's credential, which is a different thing entirely; the identity here is only
    who the commit is BY."""
    out: list[tuple[str, str, str]] = []
    for p in (*SEQUENCE, LEARN):
        out.append((p.agent, p.name, "delivery"))
    by_agent: dict[str, list[str]] = {}
    for act, agent in ACT_AGENTS.items():
        by_agent.setdefault(agent, []).append(f"maintenance: {act}")
    for agent, steps in by_agent.items():
        out.append((agent, ", ".join(steps), "maintenance"))
    out.append((PROMOTE_AGENT, "promotion: promote", "promotion"))
    return out
