"""Render the execution contract as an Argo Workflow."""
from __future__ import annotations

from orchestrator.adapters.outbound.argo.retention import gc_policy
from orchestrator.adapters.outbound.argo.worker_template import (
    _slug,
    _worker_template,
    bind_agent,
)
from orchestrator.domain.delivery import PLAYBOOK_STUDIO
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.model.git_identity import GitIdentity
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.pair_home import PairHome
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.services.delivery_launch import pinned_skill_instruction
from orchestrator.domain.services.maintenance_launch import (
    _AUTO,
    _HYGIENE,
    _NEVER,
    _VERDICT_ENDING,
    ACT_AGENTS,
    ACT_SKILLS,
    build_maintenance_prompt,
    home_directive,
)

_API = "argoproj.io/v1alpha1"

def compile_maintenance_workflow(
    repo: str,
    act: str,
    target: int | None,
    mode: MaintenanceMode,
    config: RunConfig,
    *,
    run_id: str,
    source_revision: str = "",
    credential_secret: str = "",
    feedback: str = "",
    worker_image: str = "",
    public_domain: str = "",
    namespace: str = "foundry-console",
    service_account: str = "foundry-console-worker",
    gc: dict | None = None,
    max_attempts: int = 3,
    deadline_seconds: int = 1800,
    git_identities: dict[str, GitIdentity] | None = None,
    home: PairHome | None = None,
    catalog: dict[str, CatalogAgent] | None = None,
) -> dict:
    """One maintenance drive as a submittable Argo Workflow.

    A gated or direct resolve compiles one resolve-ticket worker. A one-shot resolve
    compiles resolve-ticket then review-pr as steps - and NO merge step: the engine
    reads the verdict from GitHub after the run and merges on PASS with green checks
    (INT-FC-R65). Review compiles one review-pr worker on the selected PR;
    reconcile-docs compiles one check-run worker.
    """
    if act not in ACT_SKILLS:
        known = ", ".join(ACT_SKILLS)
        raise ValueError(f"unknown maintenance act {act!r}; one of: {known}")

    plan: list[tuple[str, str, str]] = []  # (step name, skill, prompt)
    where = home_directive(home, repo)
    if act == "resolve":
        plan.append(("resolve", ACT_SKILLS["resolve"], build_maintenance_prompt("resolve", repo, target, mode, feedback) + where))
        if mode is MaintenanceMode.ONE_SHOT:
            plan.append(("review", ACT_SKILLS["review"], (
                pinned_skill_instruction("review-pr") + f"Run review-pr for repo {repo}: review "
                f"the OPEN pull request that resolves ticket #{target} (its branch name "
                f"carries the ticket number {target}) with fresh eyes - read the diff "
                "against the ticket, the routed REFs, and the CI evidence; "
                + _VERDICT_ENDING + _NEVER + where
            )))
    else:
        plan.append((act, ACT_SKILLS[act], build_maintenance_prompt(act, repo, target, mode) + where))

    steps: list = []
    templates: list = []
    for name, skill, prompt in plan:
        tname = f"worker-{_slug(name)}"
        steps.append([{"name": _slug(name), "template": tname}])
        templates.append(
            _worker_template(
                tname,
                # Each step's completeness check keys off ITS OWN role, not the drive's act:
                # a one-shot resolve's review step must be validated as a review (a posted
                # VERDICT), not as a resolve (the resolve's own open PR), or a review that
                # crashed without posting would pass on the resolve's artifact (INT-FC-R85).
                f"maintenance:{name}",
                skill,
                repo,
                "",  # no .delivery/ record: maintenance stores no state of its own
                "",  # no gate: the verdict gate lives on the PR, not in a record
                (PLAYBOOK_STUDIO,),
                # interaction=auto on every headless maintenance worker (R78); commit hygiene
                # on every one of them too (R123), since a resolve is the path that commits.
                prompt + _AUTO + _HYGIENE,
                run_id,
                credential_secret or f"fc-run-{run_id}",
                RunMode.INTERACTIVE,  # no stamp block; maintenance gates live on GitHub
                config.worker_provider,
                config.worker_base_url,
                config.worker_model,
                worker_image,
                max_attempts,
                deadline_seconds,
                # The act's target rides to the worker so the entrypoint can verify the real
                # artifact (a resolve's open PR, a review's verdict) instead of trusting the
                # agent's bare exit code - a resolve that ends its turn before opening the PR
                # must FAIL, not read as a green run that shipped nothing. The ceremony rides
                # too, so that check expects a commit (direct) vs an open PR (gated/one-shot).
                ticket=str(target or ""),
                maint_mode=mode.value, public_domain=public_domain,
                # This step's git identity, keyed by the AGENT that runs it (the Programmer
                # resolves, the Reviewer reviews): the one place resolve and review get
                # DIFFERENT GitHub accounts, so the reviewer can approve the resolver's PR.
                # None (no identity, so no git credentials) when the operator assigned none.
                git=(git_identities or {}).get(ACT_AGENTS[name]),
                agent=bind_agent(ACT_AGENTS[name], catalog),
                # The app's home, when the foundry does not hold it: the worker clones THEIR
                # repository for the code and opens the pull request there, while the ticket
                # stays ours. Both coordinates ride, because the act spans both.
                pair=home.credential if home is not None else None,
                pair_repo=home.repo if home is not None else "",
                home_branch=home.branch if home is not None else "",
            )
        )

    templates.insert(0, {"name": "line", "steps": steps})
    for template in templates:
        if "container" in template:
            template["container"].setdefault("env", []).append({"name": "FC_SOURCE_REVISION", "value": source_revision})

    return {
        "apiVersion": _API,
        "kind": "Workflow",
        "metadata": {
            # The act rides the name so a per-act read (the docs tab's reconcile log)
            # never shows another act's run as its own.
            "generateName": f"maint-{_slug(act)}-{_slug(repo)}-",
            "namespace": namespace,
            "annotations": {"foundry-console/repository": repo},
            "labels": {
                "foundry-console/run": run_id,
                "foundry-console/maintenance": act,
                "foundry-console/mode": mode.value,
                # The judge's ledger is DERIVED from the executor (a pod restart must
                # not orphan a one-shot drive), so the run carries what the judge
                # needs: the ticket and the repo's slug (a label value cannot carry
                # the org/name slash; the fleet cache resolves the slug back).
                "foundry-console/ticket": str(target or ""),
                "foundry-console/repo-slug": _slug(repo),
            },
        },
        "spec": {
            "entrypoint": "line",
            "serviceAccountName": service_account,
            # Reclaim the worker pods and the Workflow object once the act finishes, so a
            # failed maintenance run never strands its pods either (INT-FC-R95). The
            # service passes the operator's Run retention setting as gc; absent, defaults.
            **(gc or gc_policy()),
            "templates": templates,
        },
    }
