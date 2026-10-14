"""Fleet: the whole floor, not just active deliveries.

A FleetItem joins what the Console knows about one org repo from three angles: is it a
delivery (a live scratch ref, a line in progress), is it onboarded on the platform, and
is it live. The cockpit's Fleet surface lists every project this way, so a repo that is
a shipped app, an in-flight delivery, or a plain repo all read at a glance.
"""
from __future__ import annotations

#: The role marking a repo the Foundry is built OUT OF rather than deployed as
#: (see FleetItem.role). Not a manifest role: no app entry ever carries it.
CORE = "core"

#: The DEFAULT name of the platform's own repo, used when the install names none.
#:
#: This was once a bare constant, defended as structural: one canonical source repo and
#: N deploy branches of it, so the name is identical on every install. That premise holds
#: only while every install runs the same repository. A fleet that forks the platform names
#: its own, and the constant then matched no row in the org listing - so
#: the platform repo lost its `core` marking and read as an ordinary tenant repo on the
#: board. It is an install fact after all, and FC_PLATFORM_REPO is where an install states
#: it; the default only keeps every install that has not set one working unchanged.
#:
#: A bare slug, never an org path: the fleet join matches on the normalized repo name, so
#: the org comes from the repo row the console already read.
#:
#: The playbook's slug is deliberately NOT a constant beside this one. It is asked of
#: playbook-studio, which owns the working clone and therefore cannot be stale about its
#: own upstream; a literal here would be the third authority on that one fact.
DEFAULT_PLATFORM_REPO = "foundry-platform"
