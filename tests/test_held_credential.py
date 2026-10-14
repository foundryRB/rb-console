"""The console's git token is resolved once and held (INT-FC-R143).

The behaviour under test is not "caching works". It is the two rules that make a cached
credential safe to hold: an empty resolution is never held, and an empty resolution never
evicts a good one. Both exist because every hop of the real resolution degrades to "" on a
failed read, so "" means "not configured" and "I could not tell" indistinguishably - and
holding the first reading of that ambiguity is how a working console unconfigures itself.
"""
from pytest_intent import intent

from orchestrator.application.services.settings.held_credential import HeldCredential


@intent("INT-FC-R143")
def test_the_token_is_resolved_once_not_per_read():
    calls = []

    def resolve():
        calls.append(1)
        return "ghp_real"

    held = HeldCredential(resolve)
    for _ in range(500):  # ~one org sweep's worth of outbound reads
        assert held.get() == "ghp_real"
    assert len(calls) == 1


@intent("INT-FC-R143")
def test_a_settings_write_drops_the_hold_so_a_rotation_needs_no_redeploy():
    tokens = iter(["ghp_old", "ghp_rotated"])
    held = HeldCredential(lambda: next(tokens))

    assert held.get() == "ghp_old"
    held.invalidate()
    assert held.get() == "ghp_rotated"


@intent("INT-FC-R143")
def test_an_empty_resolution_is_never_held():
    # A console that starts before its identity is assigned must keep asking. Caching the
    # absence would leave it unconfigured until a restart, with nothing to invalidate.
    answers = iter(["", "", "ghp_finally"])
    held = HeldCredential(lambda: next(answers))

    assert held.get() == ""
    assert held.get() == ""
    assert held.get() == "ghp_finally"


@intent("INT-FC-R143")
def test_an_empty_resolution_does_not_evict_a_held_token():
    # THE regression. A token does not spontaneously become empty; an empty read is a
    # failed read. Treating it as a removal is what unconfigured a working console and
    # emptied the board with copy blaming the operator's token.
    answers = iter(["ghp_real", "", "", "ghp_real"])
    held = HeldCredential(lambda: next(answers), ttl=0)  # ttl=0: re-resolve every call

    assert held.get() == "ghp_real"
    assert held.get() == "ghp_real"  # the resolve failed; the hold stands
    assert held.get() == "ghp_real"  # ...and is retried, not cached as empty
    assert held.get() == "ghp_real"


@intent("INT-FC-R143")
def test_a_raising_resolution_reads_as_a_failed_one_not_a_crash():
    # The real resolution shells out to kubectl. A raise and a "" are the same event
    # wearing different clothes, and neither may reach the caller as an exception.
    def resolve():
        raise RuntimeError("kubectl: connection refused")

    held = HeldCredential(resolve)
    assert held.get() == ""

    seeded = HeldCredential(lambda: "ghp_real", ttl=0)
    assert seeded.get() == "ghp_real"
    seeded._resolve = resolve  # the cluster goes away under a good hold
    assert seeded.get() == "ghp_real"
