---
title: "0001 · Per-phase git identities"
id: DOC-FC-ADR-0001
type: Reference
status: Active
updated: "2026-07-15"
adr_status: Decided
summary: "Every catalog agent and the console role act as their own configured machine-user identity; there is no shared or default git identity."
---

Every catalog agent and the console role act as their own configured machine-user identity; there is no shared or default git identity.

- Status: accepted
- Date: 2026-07-15
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R88, R89, R90, R91, R92
- Revised 2026-07-15: dropped the legacy shared-identity fallback. There is no seeded or
  default git identity; every identity is configured and assigned explicitly, and an
  unassigned phase (or an unassigned console role) simply has no credential. The Decision and
  Consequences below reflect this; the byte-for-byte "ship dark" compatibility path they
  originally carried is gone by intent, so no run can ever act as a hidden shared account.

## Context

Foundry Console runs its delivery and maintenance workers as Argo Workflow pods. Every run
authenticated to GitHub with a single shared credential belonging to the operator's own
account (`fc-git` / `fc-git-key`), and every console-side act (merge, comment, close, and the
org reads) used the same token.

That single-identity model has one hard failure. GitHub refuses to let an account approve its
own pull request. Because the resolver worker (which opens the PR) and the reviewer worker
(which approves it) both rode the one shared account, a one-shot review could never post an
actual *Approved* review: it fell back to a `COMMENT` carrying the `VERDICT: PASS` line
(observed on foundry-console PR #15). The self-approve block is fundamentally an
account-identity problem: as long as the token's account equals the PR author's account,
approval is refused. The only real fix is to make the reviewer a *different* account than the
author.

The operator wanted more than a single second account: the ability to assign an identity per
phase from Settings, at runtime - share one identity across a group (e.g. Delivery plus
maintenance-resolve), give Review its own, or split all of them - and to make the console's own
acts configurable the same way.

## Decision

Introduce **named git identities** and a **role -> identity map**, both runtime Settings, and
inject the assigned identity into each Job phase; resolve the console's own acts from the map
too.

- A **git identity** is a display name + commit email + GitHub login + a PAT, stored like a
  saved agent: a ConfigMap of public fields plus a write-only Secret. The token is never
  listed. (INT-FC-R88)
- A **role -> identity map** assigns each of the seven Job phases (five delivery, two
  maintenance) and the `console` role to an identity, managed at runtime. Unknown role keys are
  dropped; an empty value clears a role to unassigned (no identity). The map is blank until the
  operator fills it - nothing is seeded. (INT-FC-R90)
- The **compiler** injects each phase's identity as its own ConfigMap+Secret refs
  (`FC_GIT_USER` / `FC_GIT_EMAIL` / `FC_GIT_TOKEN`); an unassigned phase gets no git identity at
  all (no `FC_GIT_*` env), so its worker has no git credentials and cannot push until one is
  configured and assigned. Only the Secret ref travels to the pod, never the token. Compiling
  stays pure: the service resolves identities from Settings and passes them in. (INT-FC-R89)
- The **maintenance derivation** treats the *set* of the console's own identities as "ours",
  not a single login: a PR by any of them is one-shot eligible, and a review by any of them is a
  driven fresh-eyes pass (including under the one-shot judge's engine-only narrowing). This is
  what keeps one-shot auto-merge firing once author and reviewer are different accounts. A
  single-identity console is the one-element case, unchanged. (INT-FC-R91)
- The **console's own acts** (merge, comment, close, org reads) read their token from the
  identity assigned to the `console` role, resolved live so a Settings change needs no
  redeploy; with no console identity assigned there is no token and those acts refuse (there is
  no fallback secret). (INT-FC-R92)
- The **worker entrypoint** stamps `user.email` from `FC_GIT_EMAIL` (a real GitHub no-reply, so
  commits attribute to and link the machine-user) and exports `GH_TOKEN` up front so the
  agent's own `gh` calls - the resolve's `gh pr create`, the review's `gh pr review --approve` -
  act as that phase's identity.

No playbook or skill change: the skills only ever call `gh`/`git` and assume the environment is
authenticated; the console owns the identity choice entirely.

## Alternatives considered

- **GitHub App / bot identity (`foundry-bot[bot]`).** Rejected for now. An App is not a static
  token: it needs a JWT signed with the App private key exchanged for a ~1-hour installation
  token, minted in-cluster. That collides with multi-hour delivery phases (a token minted at
  submit time can expire mid-build) and adds a token-minting subsystem the codebase does not
  have. The Setting is deliberately modelled around "a token in a Secret", so an App can later
  become an optional backing (a Job refreshing that same Secret) without a schema change.
- **A single second machine-user for everything.** Insufficient on its own: if both the author
  and the reviewer ride one bot, it is self-approval again. At least two distinct accounts are
  required, which the per-phase map expresses naturally.
- **Restamp only the git author strings per phase.** Free, but cosmetic: it does nothing for
  reviews (the actual pain), cannot produce verified commits, and cannot link an avatar. Kept
  only as the commit-author layer on top of whichever identity a phase is assigned.

## Consequences

- The operator creates two machine-user accounts (e.g. `foundry-delivery-bot`,
  `foundry-review-bot`), each with a fine-grained PAT, and registers them in Settings. Assigning
  Review a different identity than Delivery/Resolve unblocks real PR approvals and takes the
  operator's own name off the runs.
- PATs are static and expire; rotation is a periodic manual chore (a calendar reminder). This is
  the trade for avoiding the App minting subsystem.
- There is no default identity, so setting up a Console is a required first step: configure the
  machine-user identities and assign them (at least to the phases the Console will run and the
  `console` role) before those runs and acts can push, merge, or read. This is deliberate - the
  cost of never letting a run act as a hidden shared account is that an unconfigured Console
  does nothing git-side until an operator wires it, and an unassigned phase fails loudly at push
  time rather than silently using a fallback.
- Verified commit badges still require commit signing and are out of scope; identity attribution
  (avatar + profile link) comes for free via the no-reply commit email.
