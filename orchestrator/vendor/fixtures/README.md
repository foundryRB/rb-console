# Inbox fixtures

The queue's contract as data: positions in, the ordered queue out, one case per file. The verdict
reader's contract sits apart, in `verdict/verdict-reader.json` (below).

`REF-Maintenance.md` §7 states the rules in prose and `sweep.py` implements them once. This
corpus is what holds a second implementation to them. A frontend that re-derives the queue in
another runtime (a desk in TypeScript, say) vendors this folder and runs its own derivation
over every case, so a rule stated here and read differently there fails a test rather than
shipping two queues that disagree about the same repo.

## Shape

```json
{
  "name": "fold-review-maps-to-ticket",
  "why": "what this case pins, and why the queue would be wrong without it",
  "input": { "positions": [...], "archived": [...], "hidden_repos": [...], "running": [...] },
  "expected": [ ... rows, in order ... ]
}
```

`input` is `derive_inbox`'s four arguments (each optional but `positions`); `expected` is its
return value, order included, since the order IS the attention contract. `hidden_repos` carries the
`foundry-hidden` TOPIC at repo scope, where a ticket's `labels` carry the same mark at issue scope:
both MARK their rows and neither drops one, so a reader can hold them back and say how many.

A position is one repo:

```json
{
  "repo": "owner/name",
  "archived": false,
  "issues": [{"number": 1, "title": "...", "labels": [], "created_at": "..."}],
  "prs": [{"number": 9, "title": "...", "head": "fix/1-slug", "body": "...",
           "checks": "green|red|pending|unknown", "verdict": "pass|fail|awaiting|unrecorded",
           "updated_at": "..."}],
  "train": {"checks": "...", "version": "...", "healthy": true,
            "deployed": "...", "next_version": "...", "unreleased_total": 0},
  "promotion": [{"target": "...", "destination": "...",
                 "state": "pending|in-flight|unproven|unreadable|current",
                 "accepted": "...", "proven": "...", "door_ref": "..."}]
}
```

`promotion` is one entry per target the repo's promotion contract declares, in the states
`REF-Promotion.md` section 6 derives. It is optional: a reader that reads no contracts omits it,
derives a queue with no promotion rows, and declares `promotion` unchecked.

A row is `{repo, signal, detail, act, number, ts, stage, hidden}`.

## The verdict reader

`verdict/verdict-reader.json` pins `decision_of` in `sweep.py`, the one reader that turns a PR's reviews
into its verdict for the sweep and the merge helper alike: raw reviews in, the verdict word and the
review that decided it out. It holds every case in one file, under `cases`:

```json
{
  "name": "counted-fail-in-any-casing",
  "why": "what this case pins",
  "input": {"author": "worker", "merger": "merger",
            "reviews": [{"state": "CHANGES_REQUESTED", "body": "...",
                         "author": {"login": "reviewer"}, "authorAssociation": "MEMBER"}]},
  "expected": {"verdict": "fail", "decided_by": 0}
}
```

`reviews` run oldest first, in the host's own shape. `verdict` is `pass`, `fail`, `unrecorded` or
`awaiting`; `decided_by` is the index in `reviews` of the review that decided it, `null` when it is
`awaiting`.

## Adding a case

A queue that disagrees with §7 is wrong, not a variant: fix `sweep.py` and add the case
here, so every reader inherits the fix. Never correct a row by hand in a report.
