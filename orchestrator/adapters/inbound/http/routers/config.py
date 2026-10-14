from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.mappers.config import driver_dto
from orchestrator.adapters.inbound.http.models.deleted_response import DeletedResponse
from orchestrator.adapters.inbound.http.models.driver_in import DriverIn
from orchestrator.adapters.inbound.http.models.driver_info import DriverInfo
from orchestrator.adapters.inbound.http.models.git_identities_response import (
    GitIdentitiesResponse,
)
from orchestrator.adapters.inbound.http.models.git_identity import GitIdentity
from orchestrator.adapters.inbound.http.models.git_identity_in import GitIdentityIn
from orchestrator.adapters.inbound.http.models.git_roles_in import GitRolesIn
from orchestrator.adapters.inbound.http.models.mcp_doors_response import (
    McpDoorsResponse,
)
from orchestrator.adapters.inbound.http.models.pair_credential import PairCredential
from orchestrator.adapters.inbound.http.models.project_assignment import (
    ProjectAssignment,
)
from orchestrator.adapters.inbound.http.models.project_assignment_in import (
    ProjectAssignmentIn,
)
from orchestrator.adapters.inbound.http.models.pair_credential_in import (
    PairCredentialIn,
)
from orchestrator.adapters.inbound.http.models.pair_credentials_response import (
    PairCredentialsResponse,
)
from orchestrator.adapters.inbound.http.models.roles_response import RolesResponse
from orchestrator.adapters.inbound.http.models.session_info import SessionInfo
from orchestrator.adapters.inbound.http.models.setting_in import SettingIn
from orchestrator.adapters.inbound.http.models.setting_response import SettingResponse
from orchestrator.adapters.inbound.http.models.team import Team
from orchestrator.adapters.inbound.http.models.team_in import TeamIn
from orchestrator.adapters.inbound.http.models.teams_response import TeamsResponse
from orchestrator.adapters.inbound.http.session import (
    OIDC_SIGN_OUT_PATH,
    _oidc_enabled,
    command_arguments,
    teams_enabled,
    viewer,
)

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/config/driver",
        response_model=DriverInfo,
        response_model_exclude_unset=True,
    )
    def get_driver() -> dict:
        return driver_dto(service.driver_config.execute())

    @router.post(
        "/api/config/driver",
        response_model=DriverInfo,
        response_model_exclude_unset=True,
    )
    def put_driver(body: DriverIn, *, request: Request) -> dict:
        return driver_dto(
            service.set_driver_config.execute(
                body.base_url, body.model, body.api_key, **command_arguments(request)
            )
        )

    @router.get(
        "/api/config/git-identities",
        response_model=GitIdentitiesResponse,
        response_model_exclude_unset=True,
    )
    def list_git_identities() -> dict:
        return {"identities": service.list_git_identities.execute()}

    @router.post(
        "/api/config/git-identities",
        response_model=GitIdentity,
        response_model_exclude_unset=True,
    )
    def set_git_identity(body: GitIdentityIn, *, request: Request) -> dict:
        try:
            return service.set_git_identity.execute(
                body.name,
                body.email,
                body.login,
                body.token,
                **command_arguments(request),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete(
        "/api/config/git-identities/{name}",
        response_model=DeletedResponse,
        response_model_exclude_unset=True,
    )
    def delete_git_identity(name: str, *, request: Request) -> dict:
        try:
            service.delete_git_identity.execute(name, **command_arguments(request))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"deleted": name}

    @router.get(
        "/api/config/pair-credentials",
        response_model=PairCredentialsResponse,
        response_model_exclude_unset=True,
    )
    def list_pair_credentials() -> dict:
        return {"credentials": service.list_pair_credentials.execute()}

    @router.post(
        "/api/config/pair-credentials",
        response_model=PairCredential,
        response_model_exclude_unset=True,
    )
    def set_pair_credential(body: PairCredentialIn, *, request: Request) -> dict:
        try:
            return service.set_pair_credential.execute(
                body.name,
                body.host,
                body.login,
                body.token,
                **command_arguments(request),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete(
        "/api/config/pair-credentials/{name}",
        response_model=DeletedResponse,
        response_model_exclude_unset=True,
    )
    def delete_pair_credential(name: str, *, request: Request) -> dict:
        try:
            service.delete_pair_credential.execute(name, **command_arguments(request))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"deleted": name}

    @router.get(
        "/api/config/git-roles",
        response_model=RolesResponse,
        response_model_exclude_unset=True,
    )
    def get_git_roles() -> dict:
        return {
            "roles": service.git_roles.execute(),
            "catalog": service.git_role_catalog.execute(),
        }

    @router.post(
        "/api/config/git-roles",
        response_model=RolesResponse,
        response_model_exclude_unset=True,
    )
    def set_git_roles(body: GitRolesIn, *, request: Request) -> dict:
        try:
            return {
                "roles": service.set_git_roles.execute(
                    body.roles, **command_arguments(request)
                ),
                "catalog": service.git_role_catalog.execute(),
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get(
        "/api/config/mcp-doors",
        response_model=McpDoorsResponse,
        response_model_exclude_unset=True,
    )
    def mcp_doors() -> dict:
        return {"doors": service.mcp_doors.execute()}

    @router.get(
        "/api/config/session",
        response_model=SessionInfo,
        response_model_exclude_unset=True,
    )
    def session(*, request: Request) -> dict:
        enabled = _oidc_enabled()
        caller = viewer(request)
        return {
            "oidc_enabled": enabled,
            "sign_out_url": OIDC_SIGN_OUT_PATH if enabled else "",
            "teams_enabled": teams_enabled(),
            "admin": caller.admin,
            "teams": sorted(caller.teams),
            "user": caller.principal_label,
        }

    @router.get(
        "/api/config/teams",
        response_model=TeamsResponse,
        response_model_exclude_unset=True,
    )
    def list_teams(*, request: Request) -> dict:
        return service.list_teams.execute(viewer=viewer(request))

    @router.post("/api/config/teams", response_model=Team, response_model_exclude_unset=True)
    def set_team(body: TeamIn, *, request: Request) -> dict:
        try:
            return service.set_team.execute(
                body.name, body.group, **command_arguments(request)
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete(
        "/api/config/teams/{name}",
        response_model=DeletedResponse,
        response_model_exclude_unset=True,
    )
    def delete_team(name: str, *, request: Request) -> dict:
        service.delete_team.execute(name, **command_arguments(request))
        return {"deleted": name}

    @router.post(
        "/api/config/team-projects",
        response_model=ProjectAssignment,
        response_model_exclude_unset=True,
    )
    def assign_project(body: ProjectAssignmentIn, *, request: Request) -> dict:
        try:
            return service.assign_project.execute(
                body.repository, body.team, **command_arguments(request)
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get(
        "/api/config/setting/{name}",
        response_model=SettingResponse,
        response_model_exclude_unset=True,
    )
    def get_setting(name: str) -> dict:
        value = service.get_setting.execute(name)
        return {
            "configured": bool(value.get("configured")),
            "fields": {
                key: str(item) for key, item in value.items() if key != "configured"
            },
        }

    @router.post(
        "/api/config/setting/{name}",
        response_model=SettingResponse,
        response_model_exclude_unset=True,
    )
    def set_setting(name: str, body: SettingIn, *, request: Request) -> dict:
        value = service.set_setting.execute(
            name, body.fields, body.secret, **command_arguments(request)
        )
        return {
            "configured": bool(value.get("configured")),
            "fields": {
                key: str(item) for key, item in value.items() if key != "configured"
            },
        }

    return router
