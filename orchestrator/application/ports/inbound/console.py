from __future__ import annotations

from dataclasses import dataclass

from orchestrator.application.ports.inbound.settings.assign_project import (
    AssignProjectPort,
)
from orchestrator.application.ports.inbound.settings.delete_team import DeleteTeamPort
from orchestrator.application.ports.inbound.settings.list_teams import ListTeamsPort
from orchestrator.application.ports.inbound.settings.set_team import SetTeamPort
from orchestrator.application.ports.inbound.settings.team_roster import TeamRosterPort
from orchestrator.application.ports.inbound.content.maintenance_substance import (
    MaintenanceSubstancePort,
)
from orchestrator.application.ports.inbound.content.phase_substance import (
    PhaseSubstancePort,
)
from orchestrator.application.ports.inbound.content.repo_file import RepoFilePort
from orchestrator.application.ports.inbound.content.repo_tree import RepoTreePort
from orchestrator.application.ports.inbound.copilot.chat import ChatPort
from orchestrator.application.ports.inbound.copilot.chat_poll import ChatPollPort
from orchestrator.application.ports.inbound.copilot.chat_start import ChatStartPort
from orchestrator.application.ports.inbound.copilot.fleet_chat import FleetChatPort
from orchestrator.application.ports.inbound.copilot.fleet_chat_start import (
    FleetChatStartPort,
)
from orchestrator.application.ports.inbound.delivery.advance import AdvancePort
from orchestrator.application.ports.inbound.delivery.close_line import CloseLinePort
from orchestrator.application.ports.inbound.delivery.drive import DrivePort
from orchestrator.application.ports.inbound.delivery.establish import EstablishPort
from orchestrator.application.ports.inbound.delivery.plan_next import PlanNextPort
from orchestrator.application.ports.inbound.delivery.reopen import ReopenPort
from orchestrator.application.ports.inbound.delivery.set_delivery_config import (
    SetDeliveryConfigPort,
)
from orchestrator.application.ports.inbound.delivery.sign_gate import SignGatePort
from orchestrator.application.ports.inbound.delivery.start import StartPort
from orchestrator.application.ports.inbound.maintenance.maintenance_close_ticket import (
    MaintenanceCloseTicketPort,
)
from orchestrator.application.ports.inbound.maintenance.maintenance_comment import (
    MaintenanceCommentPort,
)
from orchestrator.application.ports.inbound.maintenance.maintenance_drive import (
    MaintenanceDrivePort,
)
from orchestrator.application.ports.inbound.maintenance.maintenance_merge import (
    MaintenanceMergePort,
)
from orchestrator.application.ports.inbound.maintenance.maintenance_positions import (
    MaintenancePositionsPort,
)
from orchestrator.application.ports.inbound.maintenance.maintenance_switch_to_delivery import (
    MaintenanceSwitchToDeliveryPort,
)
from orchestrator.application.ports.inbound.maintenance.reconcile_maintenance_runs import (
    ReconcileMaintenanceRunsPort,
)
from orchestrator.application.ports.inbound.operations.inspect_operation import (
    InspectOperationPort,
)
from orchestrator.application.ports.inbound.operations.resolve_delegated_grant import (
    ResolveDelegatedGrantPort,
)
from orchestrator.application.ports.inbound.projections.delivery_overview import (
    DeliveryOverviewPort,
)
from orchestrator.application.ports.inbound.projections.fleet import FleetPort
from orchestrator.application.ports.inbound.projections.fleet_staleness import (
    FleetStalenessPort,
)
from orchestrator.application.ports.inbound.projections.list_deliveries import (
    ListDeliveriesPort,
)
from orchestrator.application.ports.inbound.projections.maintenance_inbox import (
    MaintenanceInboxPort,
)
from orchestrator.application.ports.inbound.projections.maintenance_state import (
    MaintenanceStatePort,
)
from orchestrator.application.ports.inbound.projections.refresh import RefreshPort
from orchestrator.application.ports.inbound.projections.snapshot_metadata import (
    SnapshotMetadataPort,
)
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.inbound.projections.studios import StudiosPort
from orchestrator.application.ports.inbound.promotion.declare_promotion_target import (
    DeclarePromotionTargetPort,
)
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.promotion.promotion_drive import (
    PromotionDrivePort,
)
from orchestrator.application.ports.inbound.promotion.promotion_options import (
    PromotionOptionsPort,
)
from orchestrator.application.ports.inbound.promotion.promotion_state import (
    PromotionStatePort,
)
from orchestrator.application.ports.inbound.runs.resume_run import ResumeRunPort
from orchestrator.application.ports.inbound.runs.run_graph import RunGraphPort
from orchestrator.application.ports.inbound.runs.run_logs import RunLogsPort
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.inbound.runs.run_status import RunStatusPort
from orchestrator.application.ports.inbound.runs.run_repository import RunRepositoryPort
from orchestrator.application.ports.inbound.runs.runs import RunsPort
from orchestrator.application.ports.inbound.runs.start_turn import StartTurnPort
from orchestrator.application.ports.inbound.runs.stop_run import StopRunPort
from orchestrator.application.ports.inbound.settings.apply_agent_to_delivery import (
    ApplyAgentToDeliveryPort,
)
from orchestrator.application.ports.inbound.settings.apply_agent_to_driver import (
    ApplyAgentToDriverPort,
)
from orchestrator.application.ports.inbound.settings.console_identity_setting import (
    ConsoleIdentitySettingPort,
)
from orchestrator.application.ports.inbound.settings.delete_agent import DeleteAgentPort
from orchestrator.application.ports.inbound.settings.delete_git_identity import (
    DeleteGitIdentityPort,
)
from orchestrator.application.ports.inbound.settings.delete_pair_credential import (
    DeletePairCredentialPort,
)
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.inbound.settings.driver_config import (
    DriverConfigPort,
)
from orchestrator.application.ports.inbound.settings.get_setting import GetSettingPort
from orchestrator.application.ports.inbound.settings.git_role_catalog import (
    GitRoleCatalogPort,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_agents import ListAgentsPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.inbound.settings.list_pair_credentials import (
    ListPairCredentialsPort,
)
from orchestrator.application.ports.inbound.settings.mcp_doors import McpDoorsPort
from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.ports.inbound.settings.pair_credential_host import (
    PairCredentialHostPort,
)
from orchestrator.application.ports.inbound.settings.pair_credential_ref import (
    PairCredentialRefPort,
)
from orchestrator.application.ports.inbound.settings.pair_credential_secret import (
    PairCredentialSecretPort,
)
from orchestrator.application.ports.inbound.settings.set_agent import SetAgentPort
from orchestrator.application.ports.inbound.settings.set_delivery_model import (
    SetDeliveryModelPort,
)
from orchestrator.application.ports.inbound.settings.set_delivery_timeout import (
    SetDeliveryTimeoutPort,
)
from orchestrator.application.ports.inbound.settings.set_driver_config import (
    SetDriverConfigPort,
)
from orchestrator.application.ports.inbound.settings.set_git_identity import (
    SetGitIdentityPort,
)
from orchestrator.application.ports.inbound.settings.set_git_roles import (
    SetGitRolesPort,
)
from orchestrator.application.ports.inbound.settings.set_pair_credential import (
    SetPairCredentialPort,
)
from orchestrator.application.ports.inbound.settings.set_setting import SetSettingPort
from orchestrator.application.ports.inbound.settings.set_target_selection import (
    SetTargetSelectionPort,
)
from orchestrator.application.ports.inbound.studios.pause_app import PauseAppPort
from orchestrator.application.ports.inbound.studios.resume_app import ResumeAppPort
from orchestrator.application.ports.inbound.studios.tool_urls import ToolUrlsPort


@dataclass(frozen=True)
class ConsoleCapabilities:
    status: StatusPort
    list_deliveries: ListDeliveriesPort
    refresh: RefreshPort
    fleet: FleetPort
    fleet_staleness: FleetStalenessPort
    studios: StudiosPort
    pause_app: PauseAppPort
    resume_app: ResumeAppPort
    delivery_overview: DeliveryOverviewPort
    delivery_config: DeliveryConfigPort
    set_target_selection: SetTargetSelectionPort
    set_delivery_config: SetDeliveryConfigPort
    set_delivery_model: SetDeliveryModelPort
    set_delivery_timeout: SetDeliveryTimeoutPort
    reopen: ReopenPort
    phase_substance: PhaseSubstancePort
    repo_tree: RepoTreePort
    repo_file: RepoFilePort
    chat: ChatPort
    fleet_chat: FleetChatPort
    chat_start: ChatStartPort
    fleet_chat_start: FleetChatStartPort
    chat_poll: ChatPollPort
    start_turn: StartTurnPort
    plan_next: PlanNextPort
    start: StartPort
    establish: EstablishPort
    close_line: CloseLinePort
    advance: AdvancePort
    drive: DrivePort
    runs: RunsPort
    run_retention: RunRetentionPort
    run_graph: RunGraphPort
    stop_run: StopRunPort
    resume_run: ResumeRunPort
    run_logs: RunLogsPort
    run_status: RunStatusPort
    run_repository: RunRepositoryPort
    sign_gate: SignGatePort
    driver_config: DriverConfigPort
    set_driver_config: SetDriverConfigPort
    maintenance_positions: MaintenancePositionsPort
    promotion_state: PromotionStatePort
    promotion_options: PromotionOptionsPort
    declare_promotion_target: DeclarePromotionTargetPort
    instantiation: InstantiationPort
    promotion_drive: PromotionDrivePort
    maintenance_state: MaintenanceStatePort
    maintenance_substance: MaintenanceSubstancePort
    maintenance_inbox: MaintenanceInboxPort
    maintenance_drive: MaintenanceDrivePort
    maintenance_merge: MaintenanceMergePort
    maintenance_comment: MaintenanceCommentPort
    maintenance_close_ticket: MaintenanceCloseTicketPort
    maintenance_switch_to_delivery: MaintenanceSwitchToDeliveryPort
    git_role_catalog: GitRoleCatalogPort
    list_git_identities: ListGitIdentitiesPort
    set_git_identity: SetGitIdentityPort
    delete_git_identity: DeleteGitIdentityPort
    git_roles: GitRolesPort
    set_git_roles: SetGitRolesPort
    tool_urls: ToolUrlsPort
    console_identity_setting: ConsoleIdentitySettingPort
    list_pair_credentials: ListPairCredentialsPort
    set_pair_credential: SetPairCredentialPort
    delete_pair_credential: DeletePairCredentialPort
    pair_credential_held: PairCredentialHeldPort
    pair_credential_secret: PairCredentialSecretPort
    pair_credential_host: PairCredentialHostPort
    pair_credential_ref: PairCredentialRefPort
    list_agents: ListAgentsPort
    set_agent: SetAgentPort
    delete_agent: DeleteAgentPort
    apply_agent_to_driver: ApplyAgentToDriverPort
    apply_agent_to_delivery: ApplyAgentToDeliveryPort
    mcp_doors: McpDoorsPort
    get_setting: GetSettingPort
    set_setting: SetSettingPort
    team_roster: TeamRosterPort
    list_teams: ListTeamsPort
    set_team: SetTeamPort
    delete_team: DeleteTeamPort
    assign_project: AssignProjectPort
    snapshot_metadata: SnapshotMetadataPort
    reconcile_maintenance_runs: ReconcileMaintenanceRunsPort
    inspect_operation: InspectOperationPort
    resolve_delegated_grant: ResolveDelegatedGrantPort
