---
title: Set up teams
id: DOC-FC-OPS-TEAMS
type: Guide
status: Active
updated: "2026-10-09"
summary: Switch an install to several teams - groups in the realm's token, the admin group, the teams and their projects - without anyone losing a project on the day.
---

With teams on, each team sees and acts on its own projects, a line a member opens joins the
member's team, and the admins see everything. Team membership is a group in the app realm; the
teams and their projects are set up in Settings.

## When to use

An install that more than one team shares, or a new team joining one that already has teams.

## Steps

1. In the app realm, make the user's groups part of the token the sign-in proxy reads: a group
   membership mapper on the console's client, claim `groups`. Full group paths are fine; the
   console reads a group with or without its leading slash.
2. Create the admin group and add every person who uses the console today, so nothing disappears
   for them when teams switch on. Create one group per team and add its members.
3. On the install's deploy branch, set `auth.teams.adminGroup` to the admin group's name and let
   Argo CD sync.
4. As an admin, open Settings, Teams. Save each team under its name with its group, then assign
   each project to its team. The projects no team holds are listed as visible to admins only.
5. Save the agents each team shares at the team level (Settings, Saved providers). A personal
   seat is saved by its owner, who alone drives the lines it is applied to. An agent the execution
   door should run on is an install agent.
6. To add a team later, create its group, save the team, and assign its projects. A member who
   opens a new line assigns it to their team as it opens; a member of several teams chooses.

With teams on, the installation-wide settings (the home co-pilot, git identities, pair
credentials, MCP doors and run retention) are an admin's to set; a member's Settings page shows
its providers and its view toggles.

## Verify

- A team member's Fleet, Inbox and runs show its team's projects alone, and its Settings page
  shows no Teams card.
- `GET /api/config/session` answers `teams_enabled: true`, with `admin` and `teams` for the
  signed-in user.
- An admin's Fleet still shows every project, the unassigned ones included.

## Read next

- [The admission module](../../modules/admission/)
- [The settings module](../../modules/settings/)
- [Decisions](../../decisions/)
