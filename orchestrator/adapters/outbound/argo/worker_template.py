"""Compile a delivery's remaining line into an Argo Workflow. Pure: given the
derived state and the run config, it returns the Workflow object the orchestrator
submits. Argo then owns the durable mechanics the engine would otherwise hand-roll:
retries (``retryStrategy``), timeouts (``activeDeadlineSeconds``), and human gates
(``suspend`` steps, in interactive mode only). This is the DECIDE step made
concrete; no model runs here.
"""
from __future__ import annotations

import json
import re

from orchestrator.adapters.outbound.records.lifecycle_codec import encode_lifecycle
from orchestrator.domain.current_lifecycle import CURRENT_PLAYBOOK_REF
from orchestrator.domain.model.agent_binding import AgentBinding
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.model.git_identity import GitIdentity
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.pair_credential import PairCredential
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.services.run_policy import _TERMINAL_EXITS

AGENT_EDITING_TOOLS = "Edit,Write,MultiEdit,NotebookEdit"
_WORKER_COMMAND = ["/usr/local/bin/worker-entrypoint.sh"]
# The step output's file: the entrypoint's FC_REFUSAL_FILE default.
REFUSAL_PATH = "/tmp/fc-refusal"

def bind_agent(name: str, catalog: dict[str, CatalogAgent] | None) -> AgentBinding | None:
    """The binding for a step's agent name: None when the step names nobody (an act the
    Console runs anonymously), else the name with its catalog entry when one was read."""
    if not name:
        return None
    return AgentBinding(name, (catalog or {}).get(name))


def _slug(text: str) -> str:
    tail = re.split(r"[\\/]", text.rstrip("/\\"))[-1] or "delivery"
    return re.sub(r"[^a-z0-9-]", "-", tail.lower()).strip("-") or "delivery"


def _env_name(door: str) -> str:
    """An env-var-safe form of a door name: playbook-studio -> PLAYBOOK_STUDIO."""
    return re.sub(r"[^A-Z0-9]", "_", door.upper())


def _worker_template(
    name: str,
    phase: str,
    skill: str,
    repo: str,
    record: str,
    gate: str,
    mcp_endpoints: tuple[str, ...],
    prompt: str,
    run_id: str,
    credential_secret: str,
    mode: RunMode,
    provider: str,
    base_url: str,
    model: str,
    image: str,
    max_attempts: int,
    deadline_seconds: int,
    ticket: str = "",
    maint_mode: str = "",
    git: GitIdentity | None = None,
    scratch_ref: str = "",
    pair: PairCredential | None = None,
    pair_repo: str = "",
    home_branch: str = "",
    promote_target: str = "",
    release: str = "",
    agent: AgentBinding | None = None,
    tool_url: str = "",
    slug: str = "",
    demo_of: str = "",
    playbook_ref: str = CURRENT_PLAYBOOK_REF,
    public_domain: str = "",
    lifecycle: LifecycleDefinition | None = None,
) -> dict:
    """A worker step. Argo retries it on failure (retryStrategy) and kills it at the
    deadline; the credential is referenced from the per-run Secret, never inlined.

    ``agent`` is WHO runs the step: the catalog agent the Console bound to it. Its name rides
    as FC_AGENT and as the template's ``foundry-console/agent`` label (what the run rows and
    the node graph read back), and when the catalog answered, its posture and character ride
    beside it: FC_AGENT_PERMISSION and FC_AGENT_WRITES for the entrypoint to honour, and
    FC_AGENT_PROMPT, the paragraph the worker runs under. A step with no binding compiles
    with the supplied execution inputs. A delivery gate's fresh-eyes review is the phase's
    own (the adversarial-review skill, run inside the worker), so no reviewer rides the step.

    ``ticket`` is set only for a maintenance worker (the issue/PR number the act targets),
    so the entrypoint's maintenance completeness check can verify the act's real artifact
    on GitHub (a resolve's open PR, a review's verdict). Empty for a delivery worker, which
    validates its ``.delivery/`` record instead. ``maint_mode`` is the ceremony (gated /
    one-shot / direct) that same check reads to know which artifact to expect - it is NOT
    ``mode`` (the RunMode), which is always INTERACTIVE for a maintenance worker.

    ``scratch_ref`` is the line's resolved scratch ref (the ``delivery/<line-id>``
    branch): the entrypoint fetches it after the clone and mounts it at ``.delivery/`` as
    a linked worktree, and every scratch commit pushes to it by explicit refspec. It is
    per-repo state the service resolved, threaded through here so compiling stays pure.
    Empty for a maintenance worker, which carries no scratch and mounts nothing.

    ``pair`` is set only for a worker performing a door onto a repository the foundry does
    NOT own: the token that pair granted us, by ref, plus the host it reaches. Only the ref
    travels. The entrypoint resolves it through a credential helper and keeps its value
    out of git config, remotes, and logs. ``promote_target`` and
    ``release`` name which declared target the door is for and what it carries, so the
    entrypoint verifies the declared door's artifact.
    """
    env = [
        {"name": "FC_PLAYBOOK_REF", "value": playbook_ref},
        {"name": "FC_PHASE", "value": phase},
        {"name": "FC_SKILL", "value": skill},
        {"name": "FC_REPO", "value": repo},
        {"name": "FC_RECORD", "value": record},
        {"name": "FC_LIFECYCLE_DEFINITION", "value": json.dumps(encode_lifecycle(lifecycle), sort_keys=True) if lifecycle is not None else ""},
        {"name": "FC_ARTIFACT", "value": next((item.artifact or "record" for item in lifecycle.phases if item.record == record), "") if lifecycle is not None else ""},
        # The line's scratch ref, resolved per repo (decision 0003): the entrypoint
        # mounts it at .delivery/ and pushes scratch commits to it by name.
        {"name": "FC_SCRATCH_REF", "value": scratch_ref},
        # The phase's gate, so a one-shot worker can close it deterministically after its
        # fresh-eyes review passes (the operator pre-authorized gates by choosing one-shot).
        {"name": "FC_GATE", "value": gate},
        {"name": "FC_DOMAIN", "value": public_domain},  # the ground's domain, for the worker's studio URLs
        {"name": "FC_MODE", "value": mode.value},
        # The record's provenance fields (REF-Delivery section 1 frontmatter): which run wrote
        # it, and a CITATION of the credential that drove it - never the secret value, which
        # arrives separately as FC_MODEL_CREDENTIAL from the Secret. The compiled prompt tells
        # the agent to hand these to the record helper when it authors its record; the harness
        # writes nothing before the review (the reviewed bytes are the agent's last commit),
        # and after it fills `run:` beside the run's `run_*` figures (the entrypoint's step 4c).
        {"name": "FC_RUN", "value": run_id},
        {"name": "FC_CREDENTIAL_REF", "value": credential_secret},
        # The maintenance act's target (issue/PR number), for the entrypoint's completeness
        # check. Empty for delivery; a delivery worker's artifact is its record, not a ticket.
        {"name": "FC_TICKET", "value": ticket},
        # The maintenance ceremony (gated/one-shot/direct), so the completeness check knows a
        # direct resolve's artifact is a commit on the default branch, not an open PR. FC_MODE
        # can't carry it: a maintenance worker's RunMode is always interactive.
        {"name": "FC_MAINT_MODE", "value": maint_mode},
        # A promotion worker's act: which declared target the door is for, and the release it
        # carries. The completeness check reads both to verify the real artifact (the pair's
        # open promote/<release> PR, or the deploy branch pinned at the release) - the same
        # never-ships-nothing rule a maintenance act is held to. Empty for every other worker.
        {"name": "FC_PROMOTE_TARGET", "value": promote_target},
        {"name": "FC_RELEASE", "value": release},
        # The pair's own owner/name, when the door is onto a repository we do not own. NOT a
        # secret, and load-bearing twice over: the entrypoint scopes the credential helper to
        # this exact path (a host-scoped helper would answer for our org too, on the pair's
        # token), and the completeness check reads their pull requests with it.
        {"name": "FC_PAIR_REPO", "value": pair_repo},
        # A MAINTENANCE worker over a foreign home: the branch their work lands on. Its
        # presence is also what tells the entrypoint to clone THEIR repository for the code
        # while the ticket stays on ours - the one difference between a Managed act and an
        # ordinary one, and the reason a promotion door (which sets FC_PAIR_REPO but no home
        # branch) does not accidentally take the same path.
        {"name": "FC_HOME_BRANCH", "value": home_branch},
        {"name": "FC_PROVIDER", "value": provider},
        {"name": "FC_BASE_URL", "value": base_url},
        {"name": "FC_MODEL", "value": model},
        {"name": "FC_MCP_ENDPOINTS", "value": ",".join(mcp_endpoints)},
        # The delivery slug, the one key every studio threads on (delivery_slug), and the
        # exporting studio's east-west URL for the gate stamper (INT-FC-R151): the same door
        # the cockpit's Sign hands the stamper. An empty URL is a phase whose gate freezes
        # nothing, or a gateway that could not name the door; the entrypoint then stamps
        # export-free, and a tooled gate handed none is refused by the stamper itself.
        {"name": "FC_SLUG", "value": slug},
        {"name": "FC_TOOL_URL", "value": tool_url},
        # The line a demo rehearses (REF-Demo): the source repository's full name, so the
        # pod log and the helper both name it; empty on every other seed.
        {"name": "FC_DEMO_OF", "value": demo_of},
        # The model credential: which model this worker thinks with. Sourced from the
        # delivery's persisted Secret (by slug) when present, else the per-run Secret.
        {"name": "FC_MODEL_CREDENTIAL", "valueFrom": {"secretKeyRef": {"name": credential_secret, "key": "worker_credential"}}},
    ]
    # Carry the bound agent name and any supplied catalog posture and character.
    env += _agent_env("FC_AGENT", agent)
    # The git identity for THIS step: the identity assigned to the step's catalog agent, its own
    # ConfigMap+Secret when the Settings map assigns one - so the Programmer's PRs and the
    # Reviewer's approvals can carry different GitHub accounts. Only the ref travels to the pod,
    # never the token. A step whose agent has NO assigned identity (git is None) injects no FC_GIT_* at all: the worker has no git
    # credentials and its push/gh fails loudly, so an identity must be configured and assigned.
    if git is not None:
        env.append({"name": "FC_GIT_USER", "valueFrom": {"configMapKeyRef": {"name": git.user_cm, "key": git.user_key, "optional": True}}})
        env.append({"name": "FC_GIT_TOKEN", "valueFrom": {"secretKeyRef": {"name": git.secret_name, "key": git.secret_key, "optional": True}}})
        # FC_GIT_EMAIL only when the identity carries one: the entrypoint keeps its synthetic
        # <user>@delivery.local default otherwise.
        if git.email_cm:
            env.append(
                {"name": "FC_GIT_EMAIL", "valueFrom": {"configMapKeyRef": {"name": git.email_cm, "key": git.email_key, "optional": True}}}
            )
    # The PAIR credential for a door onto a repository we do not own. It rides ALONGSIDE the
    # git identity, never instead of it: the identity is who the commit is authored by (ours),
    # this is what authorizes the push to their repository (theirs, granted). A door with no
    # pair ref injects nothing, and the entrypoint then performs no pair push - the compiler
    # refuses to build that workflow in the first place (see compile_promotion_workflow).
    if pair is not None:
        env.append({"name": "FC_PAIR_TOKEN", "valueFrom": {"secretKeyRef": {"name": pair.secret_name, "key": pair.secret_key, "optional": True}}})
        if pair.host_cm:
            env.append({"name": "FC_PAIR_HOST", "valueFrom": {"configMapKeyRef": {"name": pair.host_cm, "key": pair.host_key, "optional": True}}})
    # MCP access is per door and Basic auth, not one shared token: each owner door has
    # its own user + password, so the worker builds a Basic header per door.
    for door in mcp_endpoints:
        e = _env_name(door)
        env.append({"name": f"FC_MCP_{e}_USER", "valueFrom": {"configMapKeyRef": {"name": f"fc-mcp-{door}", "key": "user", "optional": True}}})
        env.append({"name": f"FC_MCP_{e}_PASS", "valueFrom": {"secretKeyRef": {"name": f"fc-mcp-{door}-key", "key": "value", "optional": True}}})

    return {
        "name": name,
        # Retry any failure up to the budget, EXCEPT a terminal stop (any exit in
        # _TERMINAL_EXITS): those fail fast, so the line parks for a human instead of the
        # executor blind-retrying a wall it cannot clear (a degraded blocker) or shrink (a
        # delivery-scale ticket). Built from the one _TERMINAL_EXITS source of truth.
        # (expression needs Argo >= 3.5; exitCode is compared as a string.)
        "retryStrategy": {
            "limit": max_attempts,
            "retryPolicy": "Always",
            "expression": " && ".join(f"lastRetry.exitCode != '{code}'" for code in _TERMINAL_EXITS),
        },
        "activeDeadlineSeconds": deadline_seconds,
        # Slug phase names into Kubernetes label values; display names can contain '+'.
        "metadata": {
            "labels": {
                "foundry-console/run": run_id,
                "foundry-console/phase": _slug(phase),
                # Who ran the step, as a label the run rows and the node graph read back from
                # the Workflow object itself - no second store, and it outlives the pod.
                **({"foundry-console/agent": agent.name} if agent is not None else {}),
            }
        },
        "container": {"image": image, "command": _WORKER_COMMAND, "args": [prompt], "env": env},
        # What the step says back, read off the file the entrypoint writes (issue #181) and
        # kept on the Workflow object, which outlives the pod: ``refusal`` is the last refusal
        # line of a step that stopped (the cockpit names it beside a failed run). The default
        # answers for a step that wrote none.
        "outputs": {
            "parameters": [
                {"name": "refusal", "valueFrom": {"path": REFUSAL_PATH, "default": ""}},
            ]
        },
    }


def _agent_env(prefix: str, binding: AgentBinding | None) -> list[dict]:
    """The env entries naming one bound agent: the name always, the catalog's posture and
    paragraph when it was read. Values only - an agent file holds no credential or endpoint
    (REF-Universe section 3), so nothing here is a ref."""
    if binding is None:
        return []
    out = [{"name": prefix, "value": binding.name}, {"name": f"{prefix}_TITLE", "value": binding.title}]
    entry = binding.catalog
    if entry is not None:
        out += [
            {"name": f"{prefix}_PERMISSION", "value": entry.permission},
            {"name": f"{prefix}_WRITES", "value": "true" if entry.writes else "false"},
            {"name": f"{prefix}_PROMPT", "value": entry.body},
        ]
    return out
