"""Render the remaining pinned delivery execution as an Argo Workflow."""
from __future__ import annotations

from orchestrator.adapters.outbound.argo.worker_template import (
    _slug,
    _worker_template,
    bind_agent,
)
from orchestrator.adapters.outbound.records.lifecycle_codec import lifecycle_digest
from orchestrator.domain.current_lifecycle import (
    CURRENT_PLAYBOOK_REF,
)
from orchestrator.domain.delivery import DEGRADED, delivery_slug, studio_project_key
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.model.delivery_state import DeliveryState

#: The runtime's editing tools, denied to a worker whose catalog posture says it may not
#: change the artifacts it works on. The same denylist the playbook's own installer renders
#: for a read-only agent, so the pod and a desk session hold the same line.
from orchestrator.domain.model.git_identity import GitIdentity
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.pair_home import PairHome
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.services.delivery_launch import build_worker_launch

_API = "argoproj.io/v1alpha1"
# The worker image is NOT a constant here: it is an install-supplied value (the registry
# owner is per-install, like FC_ORG and FC_DOMAIN), read once at the composition root
# (FC_WORKER_IMAGE, no default) and threaded in as ``worker_image``. Baking one install's
# ghcr path into source is the config-default anti-pattern (REF-AppContract section 1).
# The worker image's ENTRYPOINT (devops/worker.Dockerfile). Named explicitly so Argo's
# emissary executor runs it directly instead of looking the entrypoint up from the image
# manifest - that lookup needs the pull secret, which the workflow-controller cannot read.

# The ground's domain, so the worker builds studio MCP URLs for THIS instance. Required with
# no fallback: a default here (one ground's host) would silently point a second install's
# workers at the first install's studios (anti-pattern 19). It is set per-install on the deploy
# branch; unset, it reaches the worker empty and the entrypoint fails loud rather than guessing.

# The worker's terminal-stop exit codes (devops/worker-entrypoint.sh). Argo must NOT retry
# any of them (a blind retry cannot shrink a delivery-sized ticket, move a fix into the repo
# holding the ticket, or clear a degraded wall - it only redoes the whole phase); every other
# non-zero exit is transient and retried.
#   64 - a degraded stop the agent recorded as status: aborted: a wall it must not work
#        around (a missing authorization, a deterministic blocker).
#   65 - a delivery-scale stop: the resolve worker judged the ticket too big for a
#        maintenance scope (a rework, a new module, a new major, which REF-Maintenance §1
#        calls a delivery line, not a big ticket). Kept DISTINCT from 64 so the console can
#        tell "this ticket wants a delivery line" apart from a plain degraded blocker and
#        offer the operator "Switch to Delivery" (issue #13).
#   66 - a wrong-repo stop: the resolve worker found the ticket's fix lives in a DIFFERENT
#        repo, so this repo can hold no branch and no PR for it (issue #35). 65 and 66 are
#        the two ways a ticket can be unresolvable HERE while being perfectly valid: 65 is
#        its SIZE (too big for one PR), 66 its LOCUS (the code is somewhere else). Distinct
#        so the console can tell "switch this to a delivery line" from "this ticket is in
#        the wrong repo" - opposite operator acts.
#   67 - a session-limit stop: the agent run hit the model's own session/usage limit (issue
#        #40). Terminal for the SAME reason 64-66 are - a blind retry cannot help - but the
#        wall is the MODEL's, not the ticket's: the limit is a rolling window that resets on
#        the clock, so hammering it with the retry budget only burns every attempt against a
#        still-closed door and reports FAILED, when the run should park and wait for the
#        window to reopen. Kept DISTINCT from the degraded 64 so the console reads WHICH stop
#        it was and a workflow can be built around the session wall (a timed re-drive once the
#        limit resets) rather than around a generic degraded blocker.
#   68 - a stamp-refused stop: a one-shot gate's stamper refused to close the gate over a
#        passing fresh-eyes review (issue #181). The review is recorded and the refusal
#        written on the record, so the line reads awaiting that gate; a retry would re-run the
#        whole phase into the same closure, so the run parks for the operator's Sign.
from orchestrator.adapters.outbound.argo.retention import gc_policy
from orchestrator.domain.services.lifecycle_execution import (
    _adopted_studios,
    _remaining,
)


def delivery_home_directive(home: PairHome | None, repo: str) -> str:
    """What a delivery phase over a foreign home must be told.

    The scratch and the code have parted company, which no skill can infer from a tree: the
    records it writes go to ``.delivery/`` in OUR clone as always, the code it reads, builds
    and ships is in the home's clone at ``$FC_HOME_DIR``, and 'ship' is a pull request on
    the home at the proven-in-CI bar - there is no entry environment to prove anything live,
    so the line's done-bar is merged-on-home. The rules that follow from not owning the place
    ride along: the merge is theirs, and nothing of the foundry's is scaffolded into their
    repository.
    """
    if home is None:
        return ""
    return (
        f" IMPORTANT - this app's home is {home.repo}, which the foundry does NOT own, and its "
        f"code is NOT in this repository. Two clones sit side by side: this repo ({repo}) at "
        f"/work/repo holds the line's scratch (.delivery/) and its records, and is where every "
        f"record you write goes; the home is cloned at $FC_HOME_DIR on {home.branch}, and is "
        f"where the code you read, build and test lives. Work the CODE in $FC_HOME_DIR and the "
        f"RECORDS in /work/repo/.delivery/, never the other way round. 'Ship' for this app is a "
        f"pull request on {home.repo} against {home.branch} carrying your change - there is no "
        f"entry environment to deploy to or probe, so the bar is proven in THEIR CI and the line "
        f"is done when they merge it. Never merge it yourself, and never add the foundry's own "
        f"conformance, CI, chart, or scaffolding to their repository: adoption changes nothing "
        f"in a home we do not own. Work to their conventions and their tests."
    )


from orchestrator.domain.model.demo_source import DemoSource


def demo_directive(demo: DemoSource | None, repo: str) -> str:
    """What every phase of a demo line must be told (REF-Demo). The skills carry the how;
    this names the facts only the console holds - the source, the two fleet names, this
    line's key - and the one rule that turns an ordinary phase into a copy."""
    if demo is None:
        return ""
    return (
        f" IMPORTANT - this is a DEMO line (REF-Demo), a rehearsal of the shipped line {demo.repo}, "
        f"whose app's fleet name is `{demo.app}`. This line's key is `{delivery_slug(repo)}` and its "
        f"app's fleet name is `{demo.demo_app}`. Nothing is authored on a demo line: your phase copies "
        f"the source's deliverable into this line's own key through the demo-line skill's helper "
        f"(fetch demo_line.py from the demo-line skill over the playbook door and write it beside "
        f"the repo, never inside it), and the gate's review is that helper's fidelity check "
        f"(demo_line.py attest), never an adversarial review. Scope pins the source once with "
        f"`python demo_line.py open --repo /work/repo --source {demo.repo} --source-app {demo.app} "
        f"--app {demo.demo_app}`; every later phase reads .delivery/demo.json. Copy, never author; "
        f"rename the identity and nothing else; improve nothing in the source."
    )


def compile_workflow(
    repo: str,
    state: DeliveryState,
    config: RunConfig,
    *,
    run_id: str,
    credential_secret: str = "",
    from_phase: str | None = None,
    feedback: str = "",
    worker_image: str = "",
    public_domain: str = "",
    namespace: str = "foundry-console",
    service_account: str = "foundry-console-worker",
    max_attempts: int = 3,
    deadline_seconds: int = 3600,
    git_identities: dict[str, GitIdentity] | None = None,
    gc: dict | None = None,
    home: PairHome | None = None,
    catalog: dict[str, CatalogAgent] | None = None,
    tool_urls: dict[str, str] | None = None,
    demo: DemoSource | None = None,
    definition: LifecycleDefinition | None = None,
    playbook_ref: str = "",
) -> dict:
    """Turn the delivery's remaining line into a submittable Argo Workflow.

    ``catalog`` is the playbook's agent roster as the service read it (by name), or None
    when the studio did not answer. Every phase's worker is named for its catalog agent either
    way (the binding is the phase's own); the catalog adds the agent's posture and character
    to the step. ``git_identities`` is keyed
    by agent name: the identity the operator assigned to the Builder is the one every step
    the Builder runs commits as. ``tool_urls`` maps each declared studio
    to its east-west base URL, which rides to the phase whose gate freezes that studio's
    deliverables as FC_TOOL_URL, beside FC_SLUG (INT-FC-R151): the key that studio holds the
    delivery's project under (``studio_project_key``).

    ``home`` is set for a MANAGED app (foundry-platform#135): its scratch lives on this repo
    exactly as every other line's does, and its CODE lives in a repository the foundry does
    not own. Every phase's worker then gets two clones side by side - this repo at
    ``/work/repo`` with ``.delivery/`` mounted inside it as always, and the home beside it -
    and is told so, because an agent cannot infer from the tree it wakes up in that the
    scratch and the code have parted company.

    One worker step per remaining phase, in order. ``from_phase`` lets the operator begin
    the line past the derived pointer - adopting the upstream studios' existing work rather
    than re-running scope/design - and every compiled worker then gets those upstream doors.
    ``demo`` is set for a DEMO line (REF-Demo): every phase's prompt carries the demo
    directive naming the source and the two fleet names, and FC_DEMO_OF rides the pod.

    ``feedback`` is the gate review's second outcome (re-drive with the operator's feedback):
    it threads into the first compiled worker's prompt as a revision clause, never downstream.
    In interactive mode a ``suspend`` step follows each phase that has a gate, so the run
    pauses for a human signal and resumes on it. One-shot closes its own gates, so it inserts
    no suspend steps: a worker that cannot finish without a human simply fails and Argo
    retries, then the line fails (a degraded stop) once the retry budget is spent, and a gate
    whose stamp refuses over a passing review ends its step on the terminal stamp-refused stop,
    leaving the line awaiting that gate for the operator's Sign (issue #181).

    Refuses when the state carries no resolved scratch ref: every delivery worker mounts
    that ref and pushes it by name, so a run compiled without one burns its whole turn and
    dies late on a malformed refspec. The refusal names the reason the resolution is empty
    (the scratch-ref anomaly the derived state carries, or a line never established); the
    maintenance compiler is untouched - its workers carry no scratch.
    """
    definition = definition or state.lifecycle
    playbook_ref = playbook_ref or definition.source_ref or CURRENT_PLAYBOOK_REF
    if not state.scratch_ref:
        if state.status == DEGRADED and state.next_command:
            reason = state.next_command
        elif not state.exists:
            reason = "the repo carries no delivery/* scratch ref; establish the delivery first"
        else:
            reason = "the source resolved no delivery/* scratch ref for this line"
        raise ValueError(f"cannot compile a delivery run without the line's scratch ref: {reason}")
    remaining = _remaining(state, from_phase, definition)
    adopted = _adopted_studios(remaining[0].name if remaining else None, definition)
    # The delivery's worker timeout overrides the configured default budget.
    deadline = config.worker_timeout_seconds or deadline_seconds
    steps: list = []
    templates: list = []
    for i, phase in enumerate(remaining):
        # A gate re-drive's feedback steers the phase being revised - the FIRST compiled
        # worker only. Downstream phases read the revised record, not the review.
        launch = build_worker_launch(
            repo, phase.name, phase.skill, config, adopted_studios=adopted,
            feedback=feedback if i == 0 else "", definition=definition,
        )
        tname = f"worker-{_slug(phase.name)}"
        steps.append([{"name": _slug(phase.name), "template": tname}])
        templates.append(
            _worker_template(
                tname, phase.name, phase.skill, repo, phase.record if phase.completion == "record" else "", phase.gate,
                launch.mcp_endpoints, launch.prompt + delivery_home_directive(home, repo) + demo_directive(demo, repo),
                run_id, credential_secret or f"fc-run-{run_id}", config.mode,
                config.worker_provider, config.worker_base_url,
                config.worker_model, worker_image, max_attempts, deadline,
                git=(git_identities or {}).get(phase.agent),
                scratch_ref=state.scratch_ref, public_domain=public_domain,
                agent=bind_agent(phase.agent, catalog),
                tool_url=(tool_urls or {}).get(phase.studio, ""),
                lifecycle=definition,
                slug=studio_project_key(phase.studio, delivery_slug(repo)),
                demo_of=demo.repo if demo is not None else "",
                playbook_ref=playbook_ref,
                # The home, when the code is not here: cloned BESIDE this repo by the
                # entrypoint (a delivery worker's /work/repo stays ours, the scratch inside
                # it), and the phase builds and ships in it.
                pair=home.credential if home is not None else None,
                pair_repo=home.repo if home is not None else "",
                home_branch=home.branch if home is not None else "",
            )
        )
        if config.mode is RunMode.INTERACTIVE and phase.gate:
            gname = f"gate-{_slug(phase.gate)}"
            steps.append([{"name": gname, "template": gname}])
            templates.append({"name": gname, "suspend": {}})

    for template in templates:
        if "container" in template:
            template["container"]["env"].extend([
                {"name": "FC_LIFECYCLE_DIGEST", "value": lifecycle_digest(definition)},
                {"name": "FC_LIFECYCLE_ID", "value": definition.id},
                {"name": "FC_LIFECYCLE_VERSION", "value": definition.version},
            ])
    templates.insert(0, {"name": "line", "steps": steps})
    return {
        "apiVersion": _API,
        "kind": "Workflow",
        "metadata": {
            "generateName": f"delivery-{_slug(repo)}-",
            "namespace": namespace,
            "annotations": {"foundry-console/repository": repo, "foundry-console/scratch-ref": state.scratch_ref},
            "labels": {
                "foundry-console/run": run_id,
                "foundry-console/mode": config.mode.value,
                "foundry-console/repo-slug": _slug(repo),
            },
        },
        "spec": {
            "entrypoint": "line",
            "serviceAccountName": service_account,
            # Reclaim the worker pods and the Workflow object once the line finishes, so a
            # failed run never strands its pods (INT-FC-R95). The service passes the
            # operator's Run retention setting as gc; absent, the defaults compile.
            **(gc or gc_policy()),
            "templates": templates,
        },
    }
