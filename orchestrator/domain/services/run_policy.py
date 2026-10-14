"""Run stop and retention policy."""
_DEGRADED_EXIT = 64
_DELIVERY_SCALE_EXIT = 65
_WRONG_REPO_EXIT = 66
_SESSION_LIMIT_EXIT = 67
_STAMP_REFUSED_EXIT = 68
# The terminal exit codes, the one source of truth the retry expression is built from, so a
# new sentinel is added here once and both compilers (delivery and maintenance) inherit it.
# devops/worker-entrypoint.sh re-declares these for the shell; test_exit_contract.py holds
# the two in agreement mechanically, because a comment saying "keep in sync" is not a gate.
_TERMINAL_EXITS = (_DEGRADED_EXIT, _DELIVERY_SCALE_EXIT, _WRONG_REPO_EXIT, _SESSION_LIMIT_EXIT, _STAMP_REFUSED_EXIT)

#: What each terminal exit IS, in the console's own vocabulary. These codes are the console's
#: own protocol - it defines them here, compiles Argo's retry expression from them, and ships
#: the worker that emits them - so reading one back by name is reading its own contract, not
#: interpreting a foreign signal. A code absent from this table has no name: the surfaces fall
#: back to the executor's own word rather than labelling a stop the console does not define
#: (a container killed 137, a future code), because a confident wrong name is worse than a
#: vague true one. The errors doc page carries the prose for each; test_exit_contract.py holds
#: the page and this table in agreement.
TERMINAL_STOP_NAMES = {
    _DEGRADED_EXIT: "degraded",
    _DELIVERY_SCALE_EXIT: "delivery-scale",
    _WRONG_REPO_EXIT: "wrong-repo",
    _SESSION_LIMIT_EXIT: "session-limit",
    _STAMP_REFUSED_EXIT: "stamp-refused",
}


def stop_name(exit_code: int | str | None) -> str:
    """The stop's name for a terminal exit code, or "" when the console does not define it."""
    try:
        return TERMINAL_STOP_NAMES.get(int(exit_code), "")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""


#: WHO stopped a run, recorded as a label on the Workflow the moment the shutdown is asked
#: for. Argo has five workflow phases - Pending, Running, Succeeded, Failed, Error - and a
#: shutdown lands in Failed, so the executor's own word cannot separate a crash from a
#: deliberate close. Reporting that raw was a lie of attribution: an operator who re-drove a
#: line through a week of iterations read a wall of red "Failed" rows for runs the CONSOLE
#: had stopped on their behalf, with no way to tell them from a run that genuinely died.
#:
#: This is the same protocol shape as TERMINAL_STOP_NAMES above and holds for the same
#: reason: the console asks for the shutdown, so reading the reason back is reading its own
#: contract, not interpreting a foreign signal. It is deliberately NOT Argo's status message
#: ("Stopped with strategy 'Stop'"), which is identical for both reasons and would leave the
#: surfaces guessing at the one thing that actually differs - who acted.
STOP_LABEL = "foundry-console/stop"
#: The console stopped it: a newer drive of the same delivery took over (service._supersede_runs).
STOP_SUPERSEDED = "superseded"
#: A human pressed Stop or Terminate on the run controls.
STOP_OPERATOR = "operator"
STOP_REASONS = (STOP_SUPERSEDED, STOP_OPERATOR)

# Evidence retention is expressed as durations; executor adapters render their policy.
POD_GC_DELAY_HOURS_DEFAULT = 1
TTL_SUCCESS_DAYS_DEFAULT = 7
TTL_FAILURE_DAYS_DEFAULT = 30
