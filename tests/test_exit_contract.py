"""The worker's terminal-exit and ticket-label contracts, held across languages.

Three files declare the same constants in three languages: the compiler in Python
(the source of truth Argo's retry expression is built from), the worker entrypoint
in shell, and the maintenance pane in TypeScript. Each carried a comment asking a
human to keep them in sync, and nothing checked that a human did. These tests are
that check - the comments are now descriptions of a gate rather than the gate.
"""

from __future__ import annotations
from maintenance_fixtures import semantic_comment

import re
from pathlib import Path

import pytest
from pytest_intent import intent

from orchestrator.application.maintenance_resolver import (
    DELIVERY_SCALE_LABEL,
    WRONG_REPO_LABEL,
)
from orchestrator.domain.services.run_policy import TERMINAL_STOP_NAMES, _DEGRADED_EXIT, _DELIVERY_SCALE_EXIT, _SESSION_LIMIT_EXIT, _STAMP_REFUSED_EXIT, _TERMINAL_EXITS, _WRONG_REPO_EXIT, stop_name

_ROOT = Path(__file__).resolve().parents[1]
_ENTRYPOINT = _ROOT / "devops" / "worker-entrypoint.sh"
_PANE = _ROOT / "frontend" / "src" / "views" / "organisms" / "MaintenancePane.tsx"

# Wordings a model's session/usage wall has actually printed, which step 3a must classify as
# the session-limit stop. The first TWO are verbatim from live runs that each reopened this
# after a marker set missed them (#47: delivery alexandria, run 5cjbm, phase intent+plan,
# 2026-08-02; and delivery ai-assessment, run 1858b, phase design, 2026-08-16, where the
# quota was named for the MODEL rather than for a window). The rest are the phrasings the
# original set (#40) was written against, kept so a later widening cannot silently drop what
# already worked. This is a corpus, not a guess: every new wording a wall prints belongs here
# the day it is seen, which is the whole point of pinning it.
_SESSION_WALL_WORDINGS = (
    "You've hit your session limit - resets 7:20am (UTC)",
    "You've reached your Fable 5 limit. /model to switch models.",
    "Claude usage limit reached. Your limit will reset at 7am (UTC).",
    "session limit reached",
    "Session limit exceeded",
    "5-hour limit reached",
)

# Ordinary worker failures, which must stay transient and retried. The wall is the exception;
# widening the marker set must not swallow the common case it is carved out of.
_TRANSIENT_WORDINGS = (
    "worker: intent+plan agent exited 1 - transient, the executor will retry",
    "fatal: could not read Username for 'https://github.com'",
    "MCP tool call timed out after 600000ms",
    "Error: exit status 1",
)


def _session_wall_pattern() -> re.Pattern[str]:
    """Compile step 3a's marker set, read out of the entrypoint itself.

    Read rather than restated: a copy of the pattern here would pass while the shell the
    worker actually runs carried something else - which is precisely the drift these tests
    exist to refuse. Anchored on the marker grep's own operands so the entrypoint's other
    `grep -qiE` calls (the record's signed: checks) can never be picked up instead.
    """
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(r"grep -qiE '([^']+)' \"\$agent_raw\"", text)
    assert match, "step 3a's session-limit marker set is not in the entrypoint"
    return re.compile(match.group(1), re.IGNORECASE)


def _shell_const(name: str) -> int:
    """Read a `NAME=<int>` assignment out of the worker entrypoint."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(rf"^{name}=(\d+)$", text, re.MULTILINE)
    assert match, f"{name} is not assigned in {_ENTRYPOINT.name}"
    return int(match.group(1))


def _ts_const(name: str) -> str:
    """Read the maintained terminal label from its browser model module."""
    for source in (_ROOT / 'frontend' / 'src').rglob('*.ts*'):
        text = source.read_text(encoding='utf-8')
        match = re.search(rf"(?:export )?const {name} = '([^']+)';", text)
        if match:
            return match.group(1)
    raise AssertionError(f'{name} is missing from the browser model')


@intent("INT-FC-R113")
@pytest.mark.parametrize(
    ("shell_name", "compiled"),
    [
        ("DEGRADED_EXIT", _DEGRADED_EXIT),
        ("DELIVERY_SCALE_EXIT", _DELIVERY_SCALE_EXIT),
        ("WRONG_REPO_EXIT", _WRONG_REPO_EXIT),
        ("SESSION_LIMIT_EXIT", _SESSION_LIMIT_EXIT),
        ("STAMP_REFUSED_EXIT", _STAMP_REFUSED_EXIT),
    ],
)
def test_entrypoint_exit_codes_match_the_compiler(shell_name: str, compiled: int) -> None:
    """The worker exits with the same codes the compiler tells Argo not to retry.

    Drift here is silent and expensive in one direction: a worker exiting a code the
    compiler does not list as terminal gets RETRIED, so an unretryable stop burns its
    whole attempt budget and reports FAILED instead of parked.
    """
    assert _shell_const(shell_name) == compiled


@intent("INT-FC-R113")
def test_every_terminal_exit_is_emitted_by_the_worker() -> None:
    """No terminal code exists that nothing emits, and none is emitted but not listed."""
    emitted = {
        _shell_const("DEGRADED_EXIT"),
        _shell_const("DELIVERY_SCALE_EXIT"),
        _shell_const("WRONG_REPO_EXIT"),
        _shell_const("SESSION_LIMIT_EXIT"),
        _shell_const("STAMP_REFUSED_EXIT"),
    }
    assert emitted == set(_TERMINAL_EXITS)


@intent("INT-FC-R113")
def test_terminal_exits_are_distinct() -> None:
    """The codes carry meaning apart from "stop": the console reads WHICH stop it was."""
    assert len(set(_TERMINAL_EXITS)) == len(_TERMINAL_EXITS)


@intent("INT-FC-R117")
def test_session_limit_is_a_distinct_terminal_exit_the_worker_emits() -> None:
    """A model session/usage limit parks on its own terminal code (67), kept apart from the
    degraded 64 and the two unresolvable-here stops (65/66), and Argo refuses to retry it.

    Terminal, but for a wall the clock reopens: a blind retry only burns the attempt budget
    against a still-closed door and reports FAILED, so the run parks for a re-drive after the
    reset instead. The console reads 67 apart from a generic degraded stop, which is what lets
    a workflow be built around the session wall (issue #40). The worker must actually EXIT the
    code, not merely declare it - a constant nothing emits would park no run.
    """
    assert _SESSION_LIMIT_EXIT in _TERMINAL_EXITS
    assert _SESSION_LIMIT_EXIT not in (_DEGRADED_EXIT, _DELIVERY_SCALE_EXIT, _WRONG_REPO_EXIT)
    entrypoint = _ENTRYPOINT.read_text(encoding="utf-8")
    assert 'exit "$SESSION_LIMIT_EXIT"' in entrypoint


@intent("INT-FC-R181")
def test_a_refused_one_shot_stamp_is_a_distinct_terminal_exit_the_worker_emits() -> None:
    """A one-shot stamp that refuses over a passing review parks on its own terminal code (68),
    which Argo refuses to retry: a retry re-runs the whole phase into the same closure. Kept
    apart from the other stops so the console names it, and EMITTED by the worker, not merely
    declared: a constant nothing exits would park no run.
    """
    assert _STAMP_REFUSED_EXIT in _TERMINAL_EXITS
    assert _STAMP_REFUSED_EXIT not in (_DEGRADED_EXIT, _DELIVERY_SCALE_EXIT, _WRONG_REPO_EXIT, _SESSION_LIMIT_EXIT)
    assert stop_name(_STAMP_REFUSED_EXIT) == "stamp-refused"
    entrypoint = _ENTRYPOINT.read_text(encoding="utf-8")
    assert 'exit "$STAMP_REFUSED_EXIT"' in entrypoint


@intent("INT-FC-R117")
@pytest.mark.parametrize("wording", _SESSION_WALL_WORDINGS)
def test_the_marker_set_recognises_every_wall_wording_seen_in_the_wild(wording: str) -> None:
    """Step 3a classifies each observed session-wall line as the session-limit stop.

    The exit code was never the weak part - the CLASSIFICATION was, twice. A set that
    demanded "reached" or "exceeded" read "You've hit your session limit - resets 7:20am
    (UTC)" as an ordinary failure (issue #47); a set that then keyed on the noun before
    "limit" read "You've reached your Fable 5 limit" the same way, because that noun is the
    model's name and no list of nouns survives the next model. Each time the run retried
    into the same closed door and reported FAILED. This corpus is the only thing standing
    between the next rewording and a third repeat.
    """
    assert _session_wall_pattern().search(wording)


@intent("INT-FC-R117")
@pytest.mark.parametrize("wording", _TRANSIENT_WORDINGS)
def test_the_marker_set_leaves_ordinary_failures_transient(wording: str) -> None:
    """A clone failure, a tool timeout, or a bare non-zero exit is still retried.

    The marker set is deliberately wide - the noun phrase alone, since a false negative
    costs the whole attempt budget and a false positive costs one re-drive - so the floor
    that keeps it from swallowing every failure is checked, not assumed.
    """
    assert not _session_wall_pattern().search(wording)


@intent("INT-FC-R113")
@pytest.mark.parametrize(
    ("ts_name", "backend"),
    [
        ("DELIVERY_SCALE_LABEL", DELIVERY_SCALE_LABEL),
        ("WRONG_REPO_LABEL", WRONG_REPO_LABEL),
    ],
)
def test_worker_ticket_labels_match_the_backend(ts_name: str, backend: str) -> None:
    """The pane reads the exact label strings the loop writes.

    A typo here fails open and invisibly: the label never matches, the pane renders no
    explanation, and the parked ticket looks like an ordinary unresolved one.
    """
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert f'{ts_name}="{backend}"' in text


def _shell_str(name: str) -> str:
    """Read a `NAME="..."` assignment out of the worker entrypoint."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    assert match, f"{name} is not assigned in {_ENTRYPOINT.name}"
    return match.group(1)


@intent("INT-FC-R113")
@pytest.mark.parametrize(
    ("shell_name", "backend"),
    [
        ("DELIVERY_SCALE_LABEL", DELIVERY_SCALE_LABEL),
        ("WRONG_REPO_LABEL", WRONG_REPO_LABEL),
    ],
)
def test_entrypoint_labels_match_the_backend(shell_name: str, backend: str) -> None:
    """The worker keys its park stops on the same label strings the loop writes.

    The third language in the contract: a typo here parks nothing, so a real punt falls
    through to the PR completeness check and reports a retried transient instead.
    """
    assert _shell_str(shell_name) == backend


@intent("INT-FC-R113")
@pytest.mark.parametrize("sentinel", [".foundry-delivery-scale", ".foundry-wrong-repo"])
def test_park_sentinels_live_outside_the_clone_and_need_their_label(sentinel: str) -> None:
    """A park stop reads its sentinel from FC_SIGNAL_DIR and demands the ticket's label.

    A sentinel inside the working tree is one `git add -A` from being committed, and a
    committed sentinel is in every later clone: every subsequent run on that repo parks
    before its agent has done anything, terminally, so nothing retries and nothing shows
    why. Outside the tree it cannot be published, and the label - the durable half of the
    punt, the only half that survives the pod - is what authorizes the park.
    """
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    guard = next((ln for ln in text.splitlines() if "-f " in ln and sentinel in ln), "")
    assert guard, f"no sentinel guard for {sentinel}"
    assert "${FC_SIGNAL_DIR}/" in guard, f"{sentinel} is read from inside the clone: {guard}"
    assert "ticket_has_label" in guard, f"{sentinel} parks without checking its label: {guard}"
    # and no read of either sentinel anywhere addresses the repo root
    for line in text.splitlines():
        if sentinel in line and "#" not in line.split(sentinel)[0]:
            assert "FC_SIGNAL_DIR" in line, f"repo-root sentinel path survives: {line}"


_ERRORS_DOC = _ROOT / "docs" / "src" / "content" / "docs" / "reference" / "worker-stops.md"


@intent("INT-FC-R113")
@pytest.mark.parametrize(("code", "name"), sorted(TERMINAL_STOP_NAMES.items()))
def test_every_terminal_stop_is_documented(code: int, name: str) -> None:
    """The docs page carries a row for every stop the compiler declares.

    The fourth surface of the same table (Python, shell, pane, docs). A stop the console
    parks on and nowhere explains is the whole of issue #50: the operator reads a number,
    the number means something precise, and there is nowhere to look it up.
    """
    text = _ERRORS_DOC.read_text(encoding="utf-8")
    assert f"| {code} |" in text, f"exit {code} has no row in {_ERRORS_DOC.name}"
    assert f"`{name}`" in text, f"the stop name {name!r} is not in {_ERRORS_DOC.name}"


@intent("INT-FC-R113")
def test_stop_names_cover_the_terminal_exits_and_nothing_else() -> None:
    """Every terminal exit has a name, and only terminal exits do.

    stop_name is what the surfaces use to decide whether they may speak for a code at all,
    so an unnamed terminal exit reads as an anonymous failure and a named transient one
    labels a retry as a deliberate stop.
    """
    assert set(TERMINAL_STOP_NAMES) == set(_TERMINAL_EXITS)
    assert len(set(TERMINAL_STOP_NAMES.values())) == len(_TERMINAL_EXITS)  # names are distinct
    for code in _TERMINAL_EXITS:
        assert stop_name(code) and stop_name(str(code)) == stop_name(code)
    # anything the console does not define has no name, so its surfaces keep the executor's word
    for other in (0, 1, 137, 143, None, "", "not-a-number"):
        assert stop_name(other) == ""


# --- the pair credential's blast radius, held in the shell rather than in a comment ------
#
# A pair credential is another organization's grant, and the entrypoint is the only place it
# is ever a value rather than a ref. Three properties make that safe, and all three live in
# shell, where no Python test would otherwise reach them.

_PAIR_HELPER = re.compile(r"credential\.https://\$\{pair_host\}/\$\{FC_PAIR_REPO\}\$\{suffix\}\.helper")


@intent("INT-FC-R129")
def test_the_pair_credential_helper_is_scoped_to_the_pair_repository_not_its_host() -> None:
    """Host scoping is not enough, and the difference is the whole point.

    The common pair lives on github.com, which is our host too. A helper registered for the
    HOST would answer for our own org as well - so the day a pair's grant is the only
    credential git can find for github.com is the day something of ours is pushed on a
    partner's token. Git matches a credential config URL carrying a path only when the
    request's path matches, which is exactly the narrowing wanted.
    """
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert _PAIR_HELPER.search(text), (
        "the pair credential helper must be scoped to https://<host>/<FC_PAIR_REPO>, "
        "never to the host alone"
    )
    # ...and the guard that keeps it from ever being registered without a path to scope to.
    assert 'if [ -n "${FC_PAIR_TOKEN}" ] && [ -n "${FC_PAIR_REPO:-}" ]; then' in text


@intent("INT-FC-R129")
def test_the_pair_token_is_never_written_into_a_url_a_remote_or_a_file() -> None:
    """The pair's grant reaches git through its repository helper, over a pipe."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    # CODE only: the script's own comments name the rejected approaches on purpose (saying why
    # `url.insteadOf` was refused is worth more than the word's absence), and a test that read
    # them would forbid the explanation rather than the practice.
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    # No URL interpolation of the pair token, in any of the shapes that would embed it.
    for forbidden in (
        "x-access-token:${FC_PAIR_TOKEN}",
        "${FC_PAIR_TOKEN}@",
        "insteadOf",
        ".git-credentials",
    ):
        assert forbidden not in code, f"the pair token must never reach git via {forbidden!r}"
    # The helper reads it from the ENVIRONMENT at call time, so the file it writes carries the
    # protocol and never the secret.
    helper = text.split("<<'HELPER'", 1)[1].split("HELPER\n", 1)[0]
    assert '"$(cat "${FC_PAIR_TOKEN_FILE}")"' in helper and "printf" in helper
    assert "get" in helper  # store/erase are no-ops: git persists nothing of the pair's


@intent("INT-FC-R129")
def test_a_promotion_run_that_opened_no_door_fails_rather_than_reading_green() -> None:
    """The never-ships-nothing rule, extended to the one line whose whole job is moving proof.
    A pair's door is verified on THEIR credential, because ours cannot see their pull requests
    and asking with ours would answer for a door that was never opened."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    case = text.split("  promotion:*)", 1)[1].split("\n    ;;", 1)[0]
    # Read through the door (#167), which carries the pair's credential and their host.
    assert '"$FC_PAIR_DOOR" pr list --repo "$FC_PAIR_REPO"' in case
    door = text.split("cat > \"${WORK_DIR}/pair/door\" <<'DOOR'", 1)[1].split("\nDOOR", 1)[0]
    assert 'GH_TOKEN="$(cat "${FC_PAIR_TOKEN_FILE}")"' in door
    assert 'GH_HOST="${FC_PAIR_HOST:-github.com}"' in door
    assert case.count("exit 1") == 2  # a pair door and an environment door, each verified
    assert "fail-open" in case  # an unreachable API is unknown, never a false failure


# --- which repository a Managed act actually works in ------------------------------------


@intent("INT-FC-R131")
def test_a_managed_act_clones_the_home_and_a_promotion_door_never_takes_that_path() -> None:
    """The distinguishing input is FC_HOME_BRANCH, not FC_PAIR_REPO.

    A promotion door also carries FC_PAIR_REPO, and it must clone OUR repository - the pair is
    where it pushes TO, not from. Keying the home clone on the pair repo alone would send every
    promotion worker into the partner's tree to promote from, which is both wrong and the kind
    of wrong that still produces a plausible-looking run.
    """
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    clone = text.split("# WHICH repository holds the code", 1)[1].split('cd "${WORK_DIR}/repo"', 1)[0]
    assert 'if [ -n "${FC_HOME_BRANCH:-}" ] && [ -n "${FC_PAIR_REPO:-}" ]; then' in clone
    # Their clone carries no token in its URL: the helper answers for it, so the pair's grant
    # never lands in the .git/config of a tree we then push from.
    assert 'git clone --branch "${FC_HOME_BRANCH}" "https://${pair_host}/${FC_PAIR_REPO}.git"' in clone
    assert "FC_PAIR_TOKEN" not in clone
    # Our checkout carries the same credential-free URL in either layout.
    assert 'git clone "https://github.com/${repo_path}.git"' in clone


@intent("INT-FC-R131")
def test_a_managed_acts_completeness_check_looks_for_the_pr_where_it_actually_is() -> None:
    """The ticket is on our repo and the pull request is on theirs, so the artifact is looked
    for over there on THEIR credential: ours cannot see their pull requests, and asking with
    ours would answer for a PR that was never opened - a green run over nothing."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    case = text.split("  maintenance:*)", 1)[1].split("\n    ;;", 1)[0]
    # The coordinate AND the reader swap together, decided once: a pair's repository is
    # read through the door (#167), which is what holds their credential and their host.
    assert 'pr_repo="$FC_PAIR_REPO"' in case and 'pr_read="$FC_PAIR_DOOR"' in case
    # Every PR read follows it; none is left addressing our own repo by habit.
    assert 'gh pr list --repo "$repo_path"' not in case
    assert 'gh pr view "$prn" --repo "$repo_path"' not in case
    assert case.count('"$pr_read" pr ') == 3
    # ...and the door is what carries their grant, so no read can reach for ours instead.
    door = text.split("cat > \"${WORK_DIR}/pair/door\" <<'DOOR'", 1)[1].split("\nDOOR", 1)[0]
    assert 'GH_TOKEN="$(cat "${FC_PAIR_TOKEN_FILE}")"' in door


@intent("INT-FC-R131")
def test_the_agent_is_given_a_door_for_the_home_and_told_our_token_is_not_one() -> None:
    """The pull request on a home is an API call, and GH_TOKEN is OURS.

    git was already safe: the credential helper is scoped to the pair's repository, so a
    push carries their grant. The API was not - `gh pr create` in a clone of their tree
    reads GH_TOKEN and authenticates as us against a repository nobody granted us. The
    agent cannot see which credential reaches where, so it is handed a door and told.
    """
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    # The door is a SCRIPT, not a shell function: the agent is a separate process, and a
    # function defined in this file would be invisible to it.
    assert "cat > \"${WORK_DIR}/pair/door\" <<'DOOR'" in text
    assert 'export FC_PAIR_DOOR="${WORK_DIR}/pair/door"' in text
    door = text.split("cat > \"${WORK_DIR}/pair/door\" <<'DOOR'", 1)[1].split("\nDOOR", 1)[0]
    assert 'GH_TOKEN="$(cat "${FC_PAIR_TOKEN_FILE}")"' in door and "gh" in door
    # The secret is read from the environment at call time, never written into the file.
    assert "FC_PAIR_TOKEN" in door and "pat-" not in door
    # ...and the export of OUR token says plainly what it does not reach.
    ours = text.split("# gh reads GH_TOKEN", 1)[1].split("repo_path=", 1)[0]
    assert "FC_PAIR_DOOR" in ours and "never through plain" in ours

    # The agent is told, in the directive it actually receives.
    from orchestrator.domain.services.maintenance_launch import PairHome
    from orchestrator.domain.services.maintenance_launch import home_directive
    from orchestrator.domain.model.pair_credential import PairCredential

    directive = home_directive(
        PairHome(repo="acme/portal", branch="main",
                 credential=PairCredential(secret_name="fc-pair-x-key")),
        "org/app-foundry-side",
    )
    assert "$FC_PAIR_DOOR" in directive
    assert "acme/portal" in directive and "org/app-foundry-side" in directive
    # An app we DO own gets no door talk at all: there is no pair to reach.
    assert home_directive(None, "org/app") == ""


@intent("INT-FC-R135")
def test_a_managed_resolve_records_the_home_pr_on_our_ticket() -> None:
    """The ticket-to-PR link cannot be re-derived cross-repo, so it is RECORDED: a marked
    comment on our ticket naming the home PR, left by the entrypoint the moment it has
    proved that PR exists. By the entrypoint and not the agent, because an agent asked to
    remember a pointer is a pointer that is sometimes missing. Idempotent, so a re-drive
    that finds the same PR leaves no duplicate."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    case = text.split("  maintenance:*)", 1)[1].split("\n    ;;", 1)[0]
    # Only when the PR is somewhere other than the ticket's own repo.
    assert 'if [ "$pr_repo" != "$repo_path" ]; then' in case
    assert 'marker="<!-- foundry:home-pr https://${FC_PAIR_HOST:-github.com}/${pr_repo}/pull/${prn} -->"' in case
    # Idempotent: the existing comments are checked for the exact marker first.
    assert 'grep -qF "$marker"' in case
    assert 'gh issue comment "$tkt" --repo "$repo_path"' in case
    # ...and the marker the shell writes is the one the console reads.
    from orchestrator.domain.services.repository_door import home_pr_from_comments

    rendered = "<!-- foundry:home-pr https://github.com/acme/portal/pull/14 -->\n\nResolved in acme/portal#14, theirs to review and merge."
    assert home_pr_from_comments(tuple(semantic_comment(record) for record in ([{"body": rendered}]))) == ("acme/portal", 14)


@intent("INT-FC-R136")
def test_a_managed_delivery_gets_two_clones_and_one_shot_never_stamps_its_delivery_gate() -> None:
    """A delivery worker's /work/repo stays OURS (the scratch mounts inside it, step 1b), and
    the home is cloned BESIDE it - distinguished from the maintenance layout by the scratch
    facts a delivery carries and maintenance never does. And one-shot's standing
    pre-authorization does not reach a Managed app's delivery gate: that gate is the home's
    merge, which no review can stand in for."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    clone = text.split("# WHICH repository holds the code", 1)[1].split('cd "${WORK_DIR}/repo"', 1)[0]
    assert 'if [ -n "${FC_RECORD:-}" ] || [ -n "${FC_SCRATCH_REF:-}" ]; then' in clone
    delivery = clone.split('if [ -n "${FC_RECORD:-}" ] || [ -n "${FC_SCRATCH_REF:-}" ]; then', 1)[1].split("  else", 1)[0]
    assert 'git clone "https://github.com/${repo_path}.git" "${WORK_DIR}/repo"' in delivery
    assert 'git clone --branch "${FC_HOME_BRANCH}" "https://${pair_host}/${FC_PAIR_REPO}.git" "${WORK_DIR}/home"' in delivery
    assert 'export FC_HOME_DIR="${WORK_DIR}/home"' in delivery
    # The one-shot stamp is withheld for exactly (delivery gate) x (a home), and only there.
    assert 'if [ "${FC_MODE:-}" = "one-shot" ] && [ "${FC_ARTIFACT:-}" = "build" ] && [ -n "${FC_HOME_BRANCH:-}" ]; then' in text
    withheld = text.split('[ -n "${FC_HOME_BRANCH:-}" ]; then', 1)[1].split("elif", 1)[0]
    assert "--review-only" in withheld and "--by" not in withheld


# --- the run's figures (#115): the helper writes them, before any scratch push ----------

_RECORD_RUN_CALL = 'python3 "$FC_RECORD_RUN_HELPER" --repo'


@intent("INT-FC-R161")
def test_the_run_figures_are_written_by_the_helper_after_the_turn_and_before_any_push() -> None:
    """The keys ride whichever push follows the agent's turn, and only the helper writes them.

    Placement is the contract: after the agent's exit is known and the self-sign guard has
    run, before the stamp and before the first scratch commit the script makes on its own
    (a failing review's evidence), so a stamped, an aborted and a failed attempt all carry
    what they cost. The raw stream it reads is the one the script captured, which therefore
    outlives the helper; and a helper failure is logged, never the phase's exit.
    """
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    # ONE invocation, in the function every path calls, so the flags cannot drift between them.
    assert text.count(_RECORD_RUN_CALL) == 1
    definition = text[text.index("record_run_figures() {"):]
    definition = definition[: definition.index("\n}")]
    assert _RECORD_RUN_CALL in definition
    assert '--stream "$agent_raw"' in definition
    assert '--run "${FC_RUN:-}"' in definition and '--agent "${FC_AGENT:-}"' in definition
    assert '--model "${FC_MODEL:-}"' in definition
    assert '--started "$agent_started"' in definition and '--finished "$agent_finished"' in definition
    assert '|| echo "worker: run figures not recorded' in definition
    # The finished turn (step 4c): after the self-sign guard, before the stamp and before the
    # first scratch commit the script makes on its own.
    call = text.index("\nrecord_run_figures\n")
    assert text.index('agent_status="${PIPESTATUS[0]}"') < call
    assert text.index("strip agent-signed gate to pending") < call
    assert call < text.index('python3 "$FC_STAMP_HELPER"')
    assert call < text.index("git -C .delivery add -A")
    # The failed turn (3a): before either stop's exit, onto the record the agent had COMMITTED
    # only, pushed as one change that never alters the exit.
    failed = text.index("\n  record_run_figures_at_the_failed_turn\n")
    assert text.index('agent_status="${PIPESTATUS[0]}"') < failed
    assert failed < text.index('exit "$SESSION_LIMIT_EXIT"') and failed < text.index('exit "$agent_status"')
    at_failure = text[text.index("record_run_figures_at_the_failed_turn() {"):]
    at_failure = at_failure[: at_failure.index("\n}")]
    assert at_failure.count('git -C .delivery status --porcelain -- "$FC_RECORD"') == 2  # before and after
    assert "uncommitted at this stop" in at_failure
    assert 'git -C .delivery push origin "HEAD:refs/heads/${FC_SCRATCH_REF}"; } || true' in at_failure
    # The stream survives to the read: the cleanup is the EXIT trap's (worker_exit), set before
    # the agent runs, and no path removes it by hand before the figures are read.
    assert "trap 'worker_exit $?' EXIT" in text
    exit_handler = text[text.index("worker_exit() {"):]
    assert 'rm -f "${agent_raw:-}" "${agent_err:-}"' in exit_handler[: exit_handler.index("\n}")]
    assert text.index("trap 'worker_exit $?' EXIT") < text.index('claude -p "$PROMPT"') < failed < call
    assert 'rm -f "$agent_raw"' not in text and text.count("trap '") == 1
    # Stamped in the harness's own clock, around the agent's turn.
    assert text.index('agent_started="$(date -u') < text.index('claude -p "$PROMPT"')
    assert text.index('agent_status="${PIPESTATUS[0]}"') < text.index('agent_finished="$(date -u')
    # The helper is the entrypoint's own, baked beside the vendored ones at the same root.
    assert 'FC_RECORD_RUN_HELPER="${FC_RECORD_RUN_HELPER:-/opt/foundry/record_run.py}"' in text
    worker_df = (_ROOT / "devops" / "worker.Dockerfile").read_text(encoding="utf-8")
    assert "COPY devops/record_run.py /opt/foundry/record_run.py" in worker_df
    # ...and no shell edit writes a run key beside it.
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert not re.search(r"^\s*(sed|printf|echo)\b[^\n]*run_(tokens|cost|started)", code, re.MULTILINE)
