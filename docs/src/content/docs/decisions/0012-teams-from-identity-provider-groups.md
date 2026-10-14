---
title: "0012 · Teams from identity-provider groups"
id: DOC-FC-ADR-0012
type: Reference
status: Active
updated: "2026-10-09"
adr_status: Decided
summary: "Several teams share one install: membership comes from identity-provider groups, the team-to-project mapping and the saved agents' owner levels live in the console's settings, and every read and command is scoped to the caller's teams."
---

Several teams share one install: membership comes from identity-provider groups, the
team-to-project mapping and the saved agents' owner levels live in the console's settings, and
every read and command is scoped to the caller's teams.

- Status: accepted
- Date: 2026-10-09
- Deciders: operator (rafaelgpires)
- Intent claims: INT-FC-R183, INT-FC-R184, INT-FC-R185, INT-FC-R186, INT-FC-R187, INT-FC-R188, INT-FC-R189

## Context

One install served one group of operators, every one of whom saw and acted on every project. A
second team on the same install needs its own projects, its own lines and its own model seats,
and must not see another team's work. The identity provider already knows who belongs to which
group, and every command already carries a repository scope that refuses what lies outside it.

## Decision

- **Membership comes from identity-provider groups:** one group per team and one admin group. The
  sign-in proxy forwards the user's groups; admission resolves the admin standing and the teams
  from them. The console keeps no user store of its own.
- **Teams switch on with the admin group.** An install that names no admin group, or that serves
  without the sign-in proxy, treats every operator as an admin, as before.
- **The team-to-project mapping lives in the console's settings,** beside the saved agents,
  managed in an admin-only section of Settings. A project belongs to at most one team; a project
  assigned to none is visible to admins only.
- **A team member's scope is its teams' projects.** Every command already refuses a repository
  outside its scope; every read of the shared observation is filtered by the same scope, the
  co-pilot's grounding included.
- **Establish records the line's team in the same command,** so a new line belongs to its team
  from its first moment. A member of several teams chooses; an existing repository joins a team
  by an admin's assignment.
- **Saved agents carry an owner level:** install (everyone; admins add it), team (that team's
  members; any member adds it) and user (its owner; anyone adds their own). A line set to a
  personal seat is driven by that seat's owner alone; anyone else is refused with the reason.
- **Installation-wide settings are an admin's to write:** the home co-pilot, git identities and
  their roles, pair credentials, the MCP doors' credentials and the run retention each serve every
  team at once, so a member who could write one would reach every other team's work.
- **The execution door uses install agents only.** A seat the benchmark should run on is added
  as an install agent; there are no per-agent grants.

## Alternatives considered

- **A user and team store of the console's own.** Rejected: it duplicates what the identity
  provider holds, and drifts from it the first time someone leaves a team.
- **The team recorded in the line's scratch.** Rejected: a maintenance-only repository has no
  scratch, and moving a project between teams would rewrite the line's history.
- **Per-agent grants to the execution door.** Rejected: a second permission system beside the
  levels, for a caller whose seats an admin already chooses for the whole install.

## Consequences

- The day teams switch on, the install's operators are added to the admin group, so nothing
  disappears for them; teams and assignments are then set up from Settings.
- The realm must put the user's groups in the token the sign-in proxy reads.
- A project nobody assigned is invisible to team members until an admin assigns it.
- The observation stays one installation-wide snapshot; each read filters it, so the request
  budget does not grow with the number of teams.
- Git identities and the studios stay installation-wide: no team or personal level, and an
  admin's to write.
