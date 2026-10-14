# Promotion fixtures

Where a target stands, as data: a declared target and what it carries in, the derived position
out, one case per file.

`REF-Promotion.md` sections 5 and 6 state the rules in prose. This corpus is what holds every
implementation to them. The console derives these positions in Python and the desk derives them
in TypeScript, so no shared implementation is available to both; what IS shared is this folder,
and each suite running every case is what keeps two surfaces from disagreeing about the same
target.

## Shape

```json
{
  "name": "unchecked-is-not-proven",
  "why": "what this case pins, and why a surface would be wrong without it",
  "input": {
    "proven": "v2.1.0",
    "targets": [
      {
        "target": {"name": "...", "kind": "environment", "door": "commit", "terms": "version", "acceptance": "probe"},
        "accepted": "v2.1.0",
        "door_open": "",
        "acceptance_answers": null,
        "door_shut": ""
      }
    ]
  },
  "expected": {
    "positions": [{"name": "...", "state": "unreadable", "accepted": "v2.1.0", "door_ref": "", "detail": "..."}],
    "queue": ["..."]
  }
}
```

`input.proven` is the release the entry environment serves. Each entry of `input.targets` is one
call's arguments: the declared target, what that target carries (`accepted`, `null` when it could
not be read), a `door_open` naming a submitted door not yet landed, `acceptance_answers`, the
declared signal's answer (`null` when the target declares none or the signal was not read), and
`door_shut`, the reason the door cannot be performed at all (`""` or absent when it can be).

`door_shut` is the reason a surface could not even try, and it is judged ahead of every other
rule - see `door-shut-outranks-every-other-rule.json`. The REASON is the surface's own to supply,
because the surfaces answer it differently and truthfully: a cockpit asks the platform's own pair
credential registry, a desk asks whether its authenticated client reaches the pair at all. What
this corpus fixes is the state it derives to, the sentence the reason is composed into, and the
precedence - never the wording of the reason itself.

`expected.positions` is every target in declaration order with its derived state, and
`expected.queue` is the names in attention order with `current` dropped. Both halves matter: the
first pins the derivation of one target, the second pins the ordering across several, and the
order IS the attention contract.

## The states

| State | Means |
| --- | --- |
| `pending` | proven is ahead of what the target carries, and no door is in flight |
| `in-flight` | a door is submitted and has not landed; a second promotion is not the next act |
| `unproven` | the target carries the release and its declared acceptance answers no |
| `current` | the target carries the release and nothing is owed |
| `unreadable` | the target's own state, or its declared signal, could not be read - or its door could not be opened at all |

`unreadable` is the honest fifth and the one most easily lost. A state nothing saw is reported as
unseen, never as current: unchecked is not proven.

A shut door is `unreadable` rather than a sixth state on purpose. Whether we hold a pair's
credential is a fact about our ability to ACT, not a position the target occupies - a pair whose
credential we never received may be perfectly current, we simply cannot see it. What separates it
from every other unreadable row is the act it asks for (register the credential, not look at the
target), and that is carried by the reason in `detail`, which a surface is free to render as its
own badge.
