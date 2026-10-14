"""Trusted edge identity and installation operator admission."""

from __future__ import annotations

import hmac
import ipaddress
import os
import re
from dataclasses import replace

from fastapi import Request

from orchestrator.application.ports.inbound.command_actions import (
    ADMIN_ACTIONS,
    COMMAND_ACTIONS,
)
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.team_roster import TeamRoster, group_name
from orchestrator.domain.services.authorization_revision import authorization_revision

OIDC_SIGN_OUT_PATH = "/oauth2/sign_out"

#: The execution door (INT-FC-R173): the web tier's in-cluster listener for one configured
#: machine caller, marked on every request it forwards. It serves these operations alone,
#: and its caller holds these actions alone; the nested target selection is how applying an
#: agent and setting the phase timeout record their choice.
EXECUTION_DOOR = "execution"
EXECUTION_ROUTES = (
    ("POST", re.compile(r"/api/establish")),
    ("GET", re.compile(r"/api/agents")),
    ("POST", re.compile(r"/api/agents/[^/]+/apply-delivery")),
    ("GET", re.compile(r"/api/deliveries/config")),
    ("POST", re.compile(r"/api/deliveries/config")),
    ("POST", re.compile(r"/api/deliveries/timeout")),
    ("POST", re.compile(r"/api/deliveries/drive")),
    ("GET", re.compile(r"/api/deliveries/state")),
    ("GET", re.compile(r"/api/runs/status")),
    ("POST", re.compile(r"/api/deliveries/close")),
)
EXECUTION_ACTIONS = frozenset({
    "delivery.establish", "settings.apply_delivery", "settings.target", "delivery.configure",
    "settings.delivery_timeout", "delivery.drive", "delivery.close",
})

#: Reads with the sign-in proxy off and no admitted operator: every repository is visible,
#: as on an install with no sign-in, and no act is permitted.
OPEN_READS = CommandContext(
    principal_id="",
    initiator_kind="local",
    grant_id="",
    allowed_actions=frozenset(),
    repositories=frozenset(),
    authorization_revision="",
    installation_id="",
    admin=True,
)


def _oidc_enabled() -> bool:
    return os.environ.get("FC_OIDC_ENABLED", "").lower() in {"true", "1", "yes", "on"}


def admin_group() -> str:
    """The identity-provider group whose members are the installation's admins. Teams are
    on when the sign-in proxy fronts the install and this group is configured."""
    return group_name(os.environ.get("FC_ADMIN_GROUP", ""))


def teams_enabled() -> bool:
    return _oidc_enabled() and bool(admin_group())


def _scope(value: str) -> frozenset[str]:
    return frozenset(item.strip().lower() for item in value.split(",") if item.strip())


def installation_scope() -> frozenset[str]:
    """The operators' repository scope: `FC_REPOSITORIES`, or every repository of the
    installation's owner."""
    return _scope(
        os.environ.get("FC_REPOSITORIES", os.environ.get("FC_ORG", "").strip() + "/*")
    )


def operator_authorization_revision() -> str:
    """The revision of the operators' admission policy, which delegated grants resolve
    against: the admission kind, the issuer, the organisation, the repository scope, the
    action catalogue, the local operator and the admin group."""
    oidc = _oidc_enabled()
    return authorization_revision(
        "app-realm-edge" if oidc else "loopback-local",
        os.environ.get("FC_OIDC_ISSUER", "").rstrip("/"),
        os.environ.get("FC_ORG", "").strip(),
        installation_scope(),
        COMMAND_ACTIONS.values(),
        "" if oidc else os.environ.get("FC_LOCAL_OPERATOR", ""),
        admin_group() if oidc else "",
    )


def _groups(request: Request) -> frozenset[str]:
    """The signed-in user's groups, as the sign-in proxy forwards them: comma-separated."""
    raw = request.headers.get("X-Auth-Request-Groups", "")
    return frozenset(group_name(item) for item in raw.split(",") if group_name(item))


def _roster(request: Request) -> TeamRoster:
    app = request.scope.get("app")
    port = getattr(getattr(app, "state", None), "team_roster", None)
    return port.execute() if port is not None else TeamRoster()


def _execution_context(request: Request, organization: str) -> CommandContext:
    """The machine caller's authority, admitted only through the web tier's execution door
    with the installation's execution token, and only for the execution operations."""
    expected = os.environ.get("FC_PROXY_SECRET", "")
    supplied = request.headers.get("X-Console-Proxy-Secret", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        raise PermissionDenied("A verified execution door is required.")
    if request.headers.get("X-Console-Door", "") != EXECUTION_DOOR:
        raise PermissionDenied("The door is not recognized.")
    # The path the router dispatches on, not the URL's re-parsed form.
    path = request.scope.get("path", "")
    if not any(
        request.method == method and route.fullmatch(path)
        for method, route in EXECUTION_ROUTES
    ):
        raise PermissionDenied("The execution door does not serve this operation.")
    token = os.environ.get("FC_EXECUTION_TOKEN", "").strip()
    principal = os.environ.get("FC_EXECUTION_PRINCIPAL", "").strip()
    repositories = _scope(os.environ.get("FC_EXECUTION_REPOSITORIES", ""))
    scheme, _, bearer = request.headers.get("Authorization", "").partition(" ")
    if (
        not token
        or not principal
        or not repositories
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(token.encode(), bearer.strip().encode())
    ):
        raise PermissionDenied("A configured execution credential is required.")
    # Every effect resolves a target by name under the installation's owner, so a scope
    # under any other owner would land on the installation's own repositories.
    if any(entry.split("/", 1)[0] != organization.lower() for entry in repositories):
        raise PermissionDenied("The execution scope is outside the installation.")
    revision = authorization_revision(
        "execution-door", principal, organization, repositories, EXECUTION_ACTIONS
    )
    context = CommandContext(
        principal_id="execution#" + principal,
        initiator_kind="machine",
        grant_id=revision,
        allowed_actions=EXECUTION_ACTIONS,
        repositories=repositories,
        authorization_revision=revision,
        installation_id=organization,
        principal_label="execution#" + principal,
    )
    # A line's state and configuration are read only for the caller's own repositories.
    repo = request.query_params.get("repo", "")
    if request.method == "GET" and repo and not context.in_scope(context.repository_id(repo)):
        raise PermissionDenied("The repository is outside the execution scope.")
    return context


def command_context(request: Request) -> CommandContext:
    issuer = os.environ.get("FC_OIDC_ISSUER", "").rstrip("/")
    organization = os.environ.get("FC_ORG", "").strip()
    repositories = installation_scope()
    if not organization or not repositories:
        raise PermissionDenied("The installation repository scope is not configured.")
    if "X-Console-Door" in request.headers:
        return _execution_context(request, organization)
    revision = operator_authorization_revision()
    if _oidc_enabled():
        expected = os.environ.get("FC_PROXY_SECRET", "")
        supplied = request.headers.get("X-Console-Proxy-Secret", "")
        subject = request.headers.get("X-Auth-Request-User", "")
        if (
            not expected
            or not hmac.compare_digest(expected, supplied)
            or not issuer
            or not subject
        ):
            raise PermissionDenied("A verified edge identity is required.")
        principal = issuer + "#" + subject
        label = request.headers.get("X-Auth-Request-Email", "").strip() or subject
        kind = "operator"
    else:
        principal = os.environ.get("FC_LOCAL_OPERATOR", "")
        host = request.client.host if request.client else ""
        expected = os.environ.get("FC_PROXY_SECRET", "")
        supplied = request.headers.get("X-Console-Proxy-Secret", "")
        if expected and hmac.compare_digest(expected, supplied):
            host = request.headers.get("X-Console-Client-IP", "")
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not principal or not loopback:
            raise PermissionDenied(
                "Local commands require an explicit operator on loopback."
            )
        label = principal
        kind = "local"
    context = CommandContext(
        principal_id=principal,
        initiator_kind=kind,
        grant_id=revision,
        allowed_actions=frozenset(COMMAND_ACTIONS.values()),
        repositories=repositories,
        authorization_revision=revision,
        installation_id=organization,
        admin=True,
        principal_label=label,
    )
    if kind == "operator" and teams_enabled():
        return _with_teams(context, request)
    return context


def _with_teams(context: CommandContext, request: Request) -> CommandContext:
    """An operator's standing once teams are on. A member of the admin group keeps every
    act on the installation's scope; anyone else holds every act but the team settings,
    on the repositories assigned to their teams alone."""
    groups = _groups(request)
    roster = _roster(request)
    teams = roster.teams_of(groups)
    if admin_group() in groups:
        return replace(context, teams=teams)
    return replace(
        context,
        teams=teams,
        admin=False,
        claimable=context.repositories,
        allowed_actions=context.allowed_actions - ADMIN_ACTIONS,
        repositories=frozenset(
            repository
            for repository in roster.repositories_of(teams)
            if context.in_scope(repository)
        ),
    )


def viewer(request: Request) -> CommandContext:
    """Whose read this is. With the sign-in proxy off a read needs no operator and sees
    what an admin sees."""
    try:
        return command_context(request)
    except PermissionDenied:
        if _oidc_enabled() or "X-Console-Door" in request.headers:
            raise
        return OPEN_READS


def require_visible(request: Request, repository: str | None) -> None:
    """Refuse a read or an act naming a repository the caller does not see."""
    if not viewer(request).sees(repository):
        raise PermissionDenied("The repository is outside the caller's scope.")


def command_arguments(request: Request) -> dict:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise ValueError("Idempotency-Key is required for a command.")
    revision = request.headers.get("If-Match", "").strip()
    if revision.startswith("W/") or revision == "*" or "," in revision:
        raise ValueError("If-Match must name one strong source revision.")
    if revision.startswith('"') or revision.endswith('"'):
        if len(revision) < 3 or not (revision.startswith('"') and revision.endswith('"')):
            raise ValueError("If-Match must name one strong source revision.")
        revision = revision[1:-1]
    return {
        "context": command_context(request),
        "operation_id": key,
        "expected_revision": revision or None,
    }
