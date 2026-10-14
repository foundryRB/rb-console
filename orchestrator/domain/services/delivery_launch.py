"""Build a WorkerLaunch for a phase, deterministically. No model runs here; this is
the orchestrator deciding what to launch, not the worker running it. Executing the
plan (spawning the agent) is the single model step, and it lives in an adapter.
"""
from __future__ import annotations

from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE, CURRENT_SKILL_PATHS
from orchestrator.domain.delivery import (
    PLAYBOOK_STUDIO,
    STUDIO_BY_PHASE,
    delivery_slug,
    studio_project_key,
)
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.model.worker_launch import WorkerLaunch

#: The headless-turn fact every worker compiler's landing rule rests on (INT-FC-R158): a worker
#: is `claude -p`, which exits when its turn ends, so a job it leaves running in the background
#: dies with the pod and its notification reaches nobody. Each compiler follows it with what
#: "landed" means for its own act - a delivery phase's record, a resolve's commit or PR, a door.
HEADLESS_TURN = (
    "this is a headless, single-turn agent, and nothing wakes you after you stop. NEVER start a "
    "long-running job in the background and then wait for a completion notification"
)

# The phase->studio map is owned by the domain (delivery.STUDIO_BY_PHASE), so the
# compiler and the cross-studio view read one source. Alongside it, playbook-studio is
# always reached for the skill. Intent+plan drives no MCP door: CSD is a methodology the
# worker applies locally (intent.yaml, intent tests, the csd-intent CLI), not a server.


def mcp_doors(playbook: str = PLAYBOOK_STUDIO) -> list[str]:
    """The distinct MCP doors a worker may connect to across the whole line: the
    playbook (always, for the skill) plus each phase's owner studio, deduped and in
    line order with the playbook first. This is the single source of truth for the
    doors that need a Basic-auth credential; the Console settings pane reads it rather
    than keeping its own hand-maintained copy of the phase->studio map.
    """
    doors = [playbook]
    for studio in STUDIO_BY_PHASE.values():
        if studio and studio not in doors:
            doors.append(studio)
    return doors


def build_worker_launch(
    repo: str,
    phase: str,
    skill: str,
    config: RunConfig,
    playbook: str = "playbook-studio",
    adopted_studios: tuple[str, ...] = (),
    feedback: str = "",
    definition: LifecycleDefinition = CURRENT_LIFECYCLE,
) -> WorkerLaunch:
    tool = next((p.studio for p in definition.phases if p.name == phase), "")
    endpoints = [playbook]
    if tool and tool != playbook:
        endpoints.append(tool)
    # A mid-line start adopts the upstream phases from the studios that already hold their
    # work: add those doors so this worker can READ the adopted scope/design (from estimatekit,
    # protopane, ...) instead of the .delivery/ records a skipped phase never wrote.
    adopted = [s for s in adopted_studios if s and s not in endpoints]
    endpoints.extend(adopted)
    slug = delivery_slug(repo)
    prompt = (
        f"Run the {skill} skill for the delivery repo at {repo}, with interaction=auto. "
        f"Read the pinned skill locally at /opt/foundry/playbook/{CURRENT_SKILL_PATHS[skill]}. "
        + (f"Drive {tool}. " if tool and tool != playbook else "")
        # Pin the DELIVERY key. The cockpit links a delivery-side studio's artifact to this
        # delivery by exact slug (the repo's last path segment); a worker that coins a
        # prettier project name orphans the estimation/prototype from the delivery. Make the
        # convention the compiler already relies on enforceable where the worker acts.
        #
        # platform-studio is deliberately NOT in that list. It keys on the app's FLEET name,
        # which is a fact of its own (INT-SKELETON-001) - the namespace, the hostname, the
        # chart, the packages - and equals the repo's name only where an organisation names
        # its repositories for the apps they hold. Telling a worker to address it by the
        # delivery slug "verbatim, never a variant" is what makes it query an app that does
        # not exist, read the result as not-onboarded, and onboard a SECOND time: a duplicate
        # manifest entry, namespace, hostname and Gateway that only an offboard undoes.
        + (
            f"This delivery's key is `{slug}`. Address the delivery-side studios (estimatekit, "
            f"protopane) by the key each holds this delivery's project under, EXACTLY: estimatekit as "
            f"`{studio_project_key('estimatekit', slug)}` (scaffold and query it verbatim), and "
            f"protopane as `{studio_project_key('protopane', slug)}` (create the prototype named "
            f"`{slug}`, which protopane keys as `{studio_project_key('protopane', slug)}`, and "
            f"query it by that key) - never a reworded, hyphenated, or otherwise prettier "
            f"variant, or the cockpit cannot link the artifact to this delivery. "
            f"platform-studio is the exception: it keys on the app's fleet NAME, a separate "
            f"fact from this repository's, so address it by the name the handoff pins and "
            f"pass this repository as `repo` when onboarding. "
        )
    )
    # The image supplies the pinned record helper and gate stamper. The agent invokes the
    # record helper with the launcher's provenance when authoring its phase record.
    prompt += (
        "The playbook's pinned delivery helpers are available in this pod: "
        "the record helper at $FC_REACH_HELPER (reach_gate.py) and "
        "the gate stamper at $FC_STAMP_HELPER (stamp_gate.py). Run `python3 $FC_REACH_HELPER` "
        "wherever your skill says to run reach_gate.py, and never hand-write a record's "
        "frontmatter block. This phase's record is named by $FC_RECORD and its identity by "
        "$FC_PHASE. Pass `--definition \"$FC_LIFECYCLE_SPEC\"` to the gate stamper to use "
        "the captured phase artifact. Where the record helper takes the run's provenance, pass this pod's: "
        '--run "$FC_RUN" --mode "$FC_MODE" --credential-ref "$FC_CREDENTIAL_REF". '
        "Do not re-run the helper over a record you did not author this turn: a parked "
        "record's provenance belongs to the run that wrote it. "
    )
    if adopted:
        prompt += (
            "Upstream phases were adopted from existing studio artifacts - their .delivery/ "
            f"records are not present, so read that context from {', '.join(adopted)} rather "
            "than expecting local records. "
        )
    if feedback:
        # The gate review's second outcome: the operator rejected the record and re-drove
        # the phase. The feedback is the review's verdict - it rides the prompt verbatim so
        # the worker REVISES what exists instead of reproducing the same result from the
        # same inputs, and it is already journaled (.delivery/journal.md) by the console.
        #
        # A re-driven worker is a COLD agent: the pod is new and nothing of the prior turn's
        # reasoning survives it, so the only context it has is what the last run committed.
        # Name every piece of that trail, not just the journal - the previous phase's own
        # record, and the committed fresh-eyes review at .delivery/reviews/ (the entrypoint
        # writes <record-stem>-<date>.md there as the gate's evidence). Those findings are
        # the nearest durable thing to the conversation the pod boundary threw away; a worker
        # that reads them starts warm instead of re-deriving the same contested answer.
        prompt += (
            "The operator reviewed this phase's committed record at its gate and re-drove the "
            f"phase with this feedback: <<{feedback}>>. This is a revision, not a first pass: "
            "the studio project and the .delivery/ record already exist - apply the feedback "
            "to them, keep everything that was not contested, and recommit the record. Before "
            "you change anything, read the trail the previous run committed: the same feedback "
            "is journaled in .delivery/journal.md, and the fresh-eyes review of the record you "
            "are revising is committed under .delivery/reviews/ (the newest file whose name "
            "starts with this record's stem). Those findings tell you what the last pass was "
            "judged on - read them so you revise against them rather than re-deriving the "
            "answer the operator just contested. "
        )
    if config.mode is RunMode.ONE_SHOT:
        # Canonical frontmatter supplies gate state; one-shot authority precedes the run.
        prompt += (
            "This is a one-shot run: the operator pre-authorized the gates, and the engine "
            "stamps each one after a fresh-eyes review. Read gate state ONLY from a record's "
            "frontmatter `signed:` line - a dated stamp there IS the signature, whatever the "
            "prose says. Never hold for a human. "
        )
    # interaction=auto ALWAYS in a pod: no human is reachable inside a worker, in either
    # mode. An interactive-mode line's operator signs gates from the console between steps,
    # never inside a running pod, so a worker that stops to ask a person hangs the pod. The
    # skill resolves open decisions by the assumption protocol (REF-Delivery.md 4b), not a
    # prompt. This is broader than the one-shot clause above, which only covers gate prose.
    prompt += (
        "You are running with interaction=auto: no human is reachable inside this pod. "
        "Never prompt or wait for a person; resolve every open decision by the assumption "
        "protocol (REF-Delivery.md section 4b), record it, and continue. "
    )
    # No phase-specific close policy here: reconcile-delivery reads interaction=auto and, on
    # that path, journals its summary and LEAVES the scratch for the operator to close (the
    # console's Close-line act: tag, then remove the scratch ref) - that behaviour lives in
    # the skill, not this prompt (REF-Delivery). Under interaction=manual (a hand-run session
    # with no console) the skill closes the line itself, since there is no button to press.
    # The commit instruction, carrying two rules the agent acts on in one sentence flow.
    # (1) The scratch geometry: .delivery/ is a linked worktree of the line's own scratch
    # ref (FC_SCRATCH_REF, an orphan delivery/<line-id> branch the entrypoint mounted), so
    # scratch commits happen INSIDE the mount with `git -C .delivery` and push that ref by
    # explicit refspec - from the main tree, `git add .delivery/` would stage a gitlink,
    # not the files, and a plain `git push` targets the default branch the scratch never
    # rides. (2) Commit hygiene (INT-FC-R123): the shared build workflow rejects any
    # commit message carrying a co-author or AI-attribution trailer and release `needs`
    # that gate, so one such commit reds the branch and ships nothing. A pod reads only
    # the repo it cloned, never the operator's workspace rules, so the rule rides the
    # commit instruction; recovery is fix-forward - a pushed trailer cannot be rewritten
    # away, only out-ranged by a later commit.
    prompt += (
        "Commit this phase's .delivery/ record and artifacts from INSIDE the scratch "
        "mount: .delivery/ is a linked worktree of the line's own scratch ref (the "
        "branch named by $FC_SCRATCH_REF), so use `git -C .delivery add`, `git -C "
        ".delivery commit`, and `git -C .delivery push origin "
        "HEAD:refs/heads/$FC_SCRATCH_REF` - never `git add .delivery` from the repo "
        "root, which stages a gitlink instead of the files. Use NO co-author or "
        "AI-attribution trailer in the message: no Co-Authored-By line, no 'Generated "
        "with' line, no tool credit - CI rejects them and the branch ships nothing "
        "until a later commit clears the push range. Do not sign any gate."
    )
    # The phase must land durable work within its headless turn (INT-FC-R158).
    # In-progress records fail worker validation and consume the executor retry budget.
    prompt += (
        f" Land this phase BEFORE this run ends: {HEADLESS_TURN}. Watch CI runs, syncs, and "
        "Jobs in the FOREGROUND with a bounded polling loop - a fixed interval and a maximum "
        "number of checks - and when the bound runs out, record what you saw rather than keep "
        "waiting. Push each coherent unit of work as you land it, so nothing lives only in this pod. "
        "Before you stop, this phase's record (when it leaves one) must carry a terminal status: "
        "`gate` once its work is done, or `aborted` via $FC_REACH_HELPER for a degraded stop - "
        "never `in-progress`, which reads as a crash and is retried from a fresh clone that "
        "holds none of this turn's reasoning."
    )
    return WorkerLaunch(
        repo=str(repo),
        phase=phase,
        skill=skill,
        credential_ref=config.worker_credential or "",
        mcp_endpoints=tuple(endpoints),
        prompt=prompt,
    )


def pinned_skill_instruction(skill: str) -> str:
    """Select skill content by its stable identity within the pinned worker tree."""
    return f"Read the pinned skill locally at /opt/foundry/playbook/{CURRENT_SKILL_PATHS[skill]}. "
