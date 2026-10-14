---
title: "0003 · The delivery scratch lives on an orphan branch"
id: DOC-FC-ADR-0003
type: Reference
status: Active
updated: "2026-08-18"
adr_status: Decided
summary: "A delivery line's records live on its own orphan `delivery/<line>` branch, mounted at `.delivery/` in a working checkout and never on the default branch."
---

A delivery line's records live on its own orphan `delivery/<line>` branch, mounted at `.delivery/` in a working checkout and never on the default branch.

- Status: accepted
- Date: 2026-08-18
- Deciders: operator (rafaelgpires)
- Intent claims: revises INT-FC-R31 (discovery), INT-FC-R39 (config), INT-FC-R79 (close-line
  drain), and INT-FC-R80 (Learn pane) at implementation, plus the worker claims that touch the
  scratch; the playbook's INT-GATE-004 and the terminal's INT-006/INT-013/INT-019 follow in
  their own repos.
- Companion: REF-Delivery §1 owns the scratch contract this decision re-homes; the REF's prose
  is rewritten when the machinery lands, and this record holds the why and the mechanics.

## Context

The delivery scratch (`.delivery/`) is the only state a delivery line carries between phases:
committed and pushed after every phase so a fresh clone resumes, progress derived from which
records exist, drained at reconcile. It lives on each delivery repo's default branch, and every
reader and writer assumes that placement implicitly: the console reads and writes it through
unqualified Contents-API calls (which resolve to the default branch) and its worker pods plain-
clone; the terminal walks the checked-out working tree; the playbook's helpers resolve every
path under one `--repo` root, and the one helper that runs git (`establish_scratch.py`) commits
and pushes whatever branch is checked out.

Placing the scratch on the default branch has measurable costs:

1. **History.** Every scratch write is a default-branch commit, and the console's sign path
   commits one file per Contents-API call (the gate exports first, the record last), so a
   single line leaves dozens of `delivery:` commits interleaved with the app's real history.
   After the drain, that lifecycle noise is permanent.
2. **CI and signals.** Delivery repos' workflows trigger on push to the default branch with no
   path filter, so every scratch commit runs the full suite; a scratch-only commit turns the
   fleet inbox's default-branch check signal red or pending; `delivery:` commits inflate the
   maintenance release train's unreleased-commit counts. Two compensating mechanisms exist
   only to mute this: the shared CI's `delivery` commit type allowance and its
   `delivery -> no release` pin.
3. **Recovery.** A drained line's records are recoverable only by digging the pre-drain commit
   out of the default branch's log; the `delivered/<slug>/P<n>` tag anchors a drain commit
   whose only content is a deletion.

The org already operates orphan branches as first-class state carriers: each install's deploy
branch is an orphan the platform reconciles from (platform-studio ADR-012 carved out orphan
creation as its own writer method for exactly this shape).

## Decision

The scratch moves off the default branch onto **one orphan branch per delivery line, named
`delivery/<line-id>`**, holding the whole scratch and nothing else.

- **The line id is the line's establish date** (`delivery/2026-08-18`). The estimation phase
  cannot name the branch: `delivers: P<n>` is pinned by scope after the scratch already
  exists (the branch holds `request.md` before the door decides adopt-vs-author), and a
  mid-line rename would break resume. The establish date is always known at mint time,
  human-meaningful in a branch listing, and unique under the singleton rule below.
- **Exactly one `delivery/*` ref may exist per repo.** Multi-line delivery is not supported;
  the singleton is an **enforced invariant, not a structural assumption**: establish refuses
  to mint a second ref while one exists, and every reader treats more than one as an anomaly
  to surface, never a state to silently pick from. The ref scheme already fits the multi-line
  future; supporting it later means dropping these refusals and adding a line identity to the
  keys that today assume the repo (the console's index, the delivery slug, the studio project
  keys, the per-slug credential and model settings, the HTTP surface) - that identity work is
  deferred, the namespace is not.
- **Existence of a `refs/heads/delivery/*` ref is the "this repo carries a live delivery"
  fact.** Discovery enumerates the namespace (the console via one matching-refs call, the
  terminal via the same two-file ref-store read it already uses for `delivered/*` tags) and
  resolves the single ref; the resolved name then threads through reads, writes, and compiled
  runs as per-repo state rather than a constant.
- **Records sit at the branch root**: `proposal.md`, `design.md`, `handoff.md`, `build.md`,
  `journal.md`, `reviews/`, the gate exports - the tree that used to sit under `.delivery/`,
  without the prefix.
- **In a working checkout the scratch mounts at `.delivery/` as a linked worktree** of the
  line's branch, and `.delivery/` is git-ignored on the default branch. The on-disk shape
  is byte-identical to the contract every helper, prompt, and pane assumes
  (`<repo>/.delivery/proposal.md`), so the gate helpers stay pure single-root file I/O and the
  skills' instructions keep their paths. The scratch is still committed - on its own ref; only
  the ref changed, not the committed-and-pushed handover contract.
- **Scratch commits and pushes name the ref explicitly** (`git -C .delivery push origin
  delivery/<line-id>`; Contents-API writes carry the resolved ref as `branch:`). The degraded
  stop on the first failed push is unchanged, applied per ref.
- **Close is tag-then-delete.** Reconcile at a terminal, or the console's Close-line act,
  mints the annotated `delivered/<slug>/P<n>` tag on the branch tip and pushes it **before**
  deleting the line's ref. The tag is both the durable delivered-marker (unchanged) and the
  anchor that keeps the line's history reachable: an annotated tag pointing into the orphan
  history prevents its garbage collection, and a fresh clone carries every delivered line's
  full record trail via its tag (`git show delivered/<slug>/P<n>:build.md`). A deliberately
  abandoned line keeps its branch and mints no tag, which is what leaves its phase revisable -
  the same semantics as an undrained scratch today.
- **`build.md` frontmatter carries `attests: <default-branch SHA>`** - the commit the
  evidence chain verified live. A single branch used to give the stamp a causal order over the
  build commits it attests; split refs forfeit that order, so the record pins it explicitly
  (the same phase-owned extra-field pattern as `delivers:` and `onboarding_pr:`).
- The `learned:` journal stamp and the unattended-close split are unchanged: `interaction=auto`
  stamps the journal and leaves the branch for the operator's Close-line act; the act itself
  becomes tag-then-delete-ref instead of a deletion commit on the default branch.

## Alternatives considered

- **Stay on the default branch.** Rejected: the costs in Context, and the fact that two shared
  CI mechanisms exist solely to compensate for scratch commits the app's history never wanted.
- **A flat, fixed `delivery` branch name.** Rejected: git's ref namespace cannot hold
  `delivery` and `delivery/<x>` in one repo at once, so the flat name is a dead end the
  multi-line future would have to migrate out of; and its only advantage - probing a known
  name without enumeration - saves one matching-refs call that both readers already pay in
  kind for the `delivered/*` tag scan. Naming lines now costs a resolved ref where a constant
  would have sat; that is the whole price, and it buys never migrating the ref scheme again.
- **Keep the `.delivery/` prefix inside the branch's tree.** Rejected: a worktree could then
  not reproduce the on-disk contract at `<repo>/.delivery`, so every helper, worker prompt,
  and pane would need a scratch-root parameter, and every API read would carry the prefix
  anyway. Branch-root plus the mount preserves the entire on-disk contract for free.
- **Name the line after its estimation phase (`delivery/P<n>`).** Rejected: the phase is
  pinned by scope after the branch must already exist, and renaming mid-line breaks resume.
  The phase pin stays where it is authoritative, in the proposal record's `delivers:` field.
- **Keep the scratch out of git entirely.** Rejected long ago (REF-Delivery anti-pattern 21):
  resumability from a fresh clone is the contract's point.
- **Mint the `delivered/` tag on a default-branch commit instead of the orphan tip.**
  Rejected: the close commit is scratch lifecycle, not code, and tagging the default branch
  would re-couple the two histories this decision separates. The `attests:` field answers
  "which code shipped" precisely, per record.

## Consequences

- Delivery repos' default-branch history carries only the app's own commits. Their CI, the
  fleet inbox's check signal, and the release train never see scratch commits again, with no
  workflow change (triggers already filter to the default branch). The shared CI's `delivery`
  type allowance and no-release pin become dormant guards rather than load-bearing mutes.
- The `.gitignore` contract inverts: delivery repos ignore `.delivery/` on the default branch
  (it is the worktree mount point). Anti-pattern 21's wording is rewritten at implementation -
  the sin was never the ignore line, it was an uncommitted scratch.
- The scratch ref is resolved state, not a constant. Every reader becomes ref-aware. Console:
  one matching-refs call resolves the line's ref, which then rides every read (`?ref=`), every
  write (`branch:`), and every compiled run (a scratch-ref env the worker receives); orphan
  creation goes through the git-data API at establish (the ADR-012 shape; delivery repos are
  auto-initialised, so git-data works); Close-line becomes tag-plus-ref-delete; the worker pod
  clones the default branch then mounts the scratch worktree - after which its degraded-exit
  checks read the tree they always meant to. Terminal: engagement detection and change
  detection move to the ref store (the walk yields the ref name and its tip SHA in the same
  two-file read, and the SHA is a cheap change detector the working-tree walk never had), and
  the desk materialises and refreshes the worktree so operator edits, the stamp helper, and
  re-drive journaling keep working on disk. Playbook: `establish_scratch.py` mints the line id,
  refuses a second live ref, creates the orphan branch and the worktree, path-scopes its
  commit, and pushes with an explicit refspec; REF-Delivery §1 and the affected anti-patterns
  are rewritten.
- Migration is one atomic act per repo with a live scratch: create the line's branch from the
  scratch subtree (line id = the line's start date read from its earliest record, or the
  migration date when none is parseable), remove `.delivery/` from the default branch, add the
  ignore. Readers must see either the old shape or the new, never half - every console
  degraded-exit is "the record is missing from the tree I read"-shaped, so a half-migrated
  repo would terminally degrade its phases.
- History retention rides on the annotated tag. The close ordering (tag, push tag, delete ref)
  is mandatory; deleting the branch untagged makes the line's history collectable. Follow-on
  lines read a prior line's records directly through its tag, which is simpler than today's
  dig through the default branch's pre-drain history.
- Published prose that narrates the on-main contract (the console and terminal docs, the
  vf-library flyers describing the delivery line) is revised through each surface's own loop
  when the machinery lands.
