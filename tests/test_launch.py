"""Tests for the worker launch-plan builder: the orchestrator decides what to
launch (pure code); the worker later runs it (the one model step)."""
from pytest_intent import intent

from orchestrator.domain.services.delivery_launch import HEADLESS_TURN, build_worker_launch
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode

CFG = RunConfig(worker_credential="tok", repo_target="acme", repo_rights=True)


@intent("INT-FC-R09")
def test_launch_plan_names_skill_repo_credential_and_endpoints():
    plan = build_worker_launch("/w/acme", "scope", "deliver-engagement", CFG)
    assert plan.skill == "deliver-engagement"
    assert plan.repo == "/w/acme"
    assert plan.credential_ref == "tok"
    assert "playbook-studio" in plan.mcp_endpoints
    assert "estimatekit" in plan.mcp_endpoints
    assert "do not sign any gate" in plan.prompt.lower()


@intent("INT-FC-R57")
def test_launch_prompt_pins_the_delivery_key_to_the_repo_slug():
    # A GitHub full_name and a local path both resolve to the same bare slug, and the
    # prompt pins that exact key so the worker cannot coin a prettier studio project name
    # (the drift that orphaned `shattered-catacombs` from repo `shatteredcatacombs`).
    for repo in ("Example-Org-Of-Engineering/shatteredcatacombs", "/w/shatteredcatacombs"):
        plan = build_worker_launch(repo, "scope", "deliver-engagement", CFG)
        assert "`shatteredcatacombs`" in plan.prompt
        low = plan.prompt.lower()
        assert "delivery's key" in low and "exactly" in low and "verbatim" in low


@intent("INT-FC-R57")
def test_launch_prompt_excludes_platform_studio_from_the_verbatim_rule():
    """The verbatim-slug rule binds the DELIVERY-side studios only.

    platform-studio keys on the app's fleet name, a fact of its own that equals the
    repository's only where an organisation names its repositories for the apps they hold.
    A prompt that swept it into "address every studio by this slug, never a variant" made a
    worker query an app that does not exist, read that as not-onboarded, and onboard a
    SECOND time - a duplicate manifest entry, namespace, hostname and Gateway that only an
    offboard undoes. The rule must name the two it governs and exempt the third.
    """
    plan = build_worker_launch("Example-Org-Of-Engineering/shatteredcatacombs", "scope",
                               "deliver-engagement", CFG)
    low = plan.prompt.lower()
    # The rule names the studios it binds...
    assert "estimatekit, protopane" in low
    # ...and never claims to bind every studio.
    assert "every studio" not in low
    # platform-studio is named as the exception, keyed on the app's name, and the worker is
    # told to pass the repository explicitly rather than let it default to that name.
    assert "platform-studio is the exception" in low
    assert "`repo`" in plan.prompt


@intent("INT-FC-R77")
def test_launch_prompt_tells_every_worker_interaction_is_auto():
    # A worker pod is headless claude -p with no human reachable (INT-FC-R39), so every
    # launch tells the skill interaction=auto and forbids prompting - in BOTH modes, since
    # even an interactive-mode line's gates are signed from the Console, never inside a pod.
    for mode in (RunMode.ONE_SHOT, RunMode.INTERACTIVE):
        cfg = RunConfig(worker_credential="tok", repo_target="acme", repo_rights=True, mode=mode)
        plan = build_worker_launch("/w/acme", "design", "design-session", cfg)
        low = plan.prompt.lower()
        assert "interaction=auto" in low
        assert "no human is reachable" in low


@intent("INT-FC-R123")
def test_launch_prompt_forbids_a_co_author_trailer_on_every_phase():
    # The shared build workflow's commit-hygiene gate rejects a co-author/AI-attribution
    # trailer and release `needs` it, so one such commit reds the branch and ships nothing.
    # A pod reads only the repo it cloned, never the operator's workspace rules, so the rule
    # has to ride the prompt. Every phase and both modes commit, so every one carries it.
    for mode in (RunMode.ONE_SHOT, RunMode.INTERACTIVE):
        cfg = RunConfig(worker_credential="tok", repo_target="acme", repo_rights=True, mode=mode)
        for phase, skill in (
            ("scope", "deliver-engagement"),
            ("design", "design-session"),
            ("build", "run-delivery-plan"),
            ("learn", "reconcile-delivery"),
        ):
            low = build_worker_launch("/w/acme", phase, skill, cfg).prompt.lower()
            assert "co-authored-by" in low
            assert "no co-author or ai-attribution trailer" in low


@intent("INT-FC-R80")
def test_learn_launch_defers_the_close_to_the_skill():
    # The interaction-aware close (journal-and-leave on auto, close-the-line on manual) is
    # the reconcile-delivery skill's job, reached via the interaction=auto the launcher
    # already passes (R77). The console must NOT re-implement it as a prompt override, so
    # the learn launch carries no bespoke close/keep policy - just the ordinary phase tail.
    plan = build_worker_launch("/w/acme", "learn", "reconcile-delivery", CFG)
    low = plan.prompt.lower()
    assert "interaction=auto" in low  # the skill reads this to choose its path
    assert "drain" not in low  # no bespoke scratch-disposal policy leaked into the prompt
    assert "do not delete" not in low
    assert "commit this phase's .delivery/ record" in low  # the ordinary tail, nothing learn-special


@intent("INT-FC-R158")
def test_launch_prompt_forbids_parking_on_a_background_job_in_every_phase():
    # A worker is `claude -p`: its turn ending ends the pod, and a background job's notification
    # reaches nobody. A record left `in-progress` reads as a crash and is retried from a fresh
    # clone, so every phase in both modes polls in the foreground and stops on a terminal status.
    for mode in (RunMode.ONE_SHOT, RunMode.INTERACTIVE):
        cfg = RunConfig(worker_credential="tok", repo_target="acme", repo_rights=True, mode=mode)
        for phase, skill in (
            ("scope", "deliver-engagement"),
            ("design", "design-session"),
            ("intent+plan", "intent-session"),
            ("build+ship", "run-delivery-plan"),
            ("learn", "reconcile-delivery"),
        ):
            low = build_worker_launch("/w/acme", phase, skill, cfg).prompt.lower()
            assert HEADLESS_TURN.lower() in low
            assert "foreground with a bounded polling loop" in low
            assert "push each coherent unit" in low
            assert "never `in-progress`" in low and "`aborted`" in low
