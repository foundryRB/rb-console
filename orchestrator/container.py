"""Typed capability assembly and process-scoped adapter wiring."""

from __future__ import annotations

from dataclasses import fields
from typing import TypeVar, get_type_hints

from orchestrator.adapters.outbound.archives.operation_receipt_store import (
    OperationReceiptStore,
)
from orchestrator.adapters.outbound.argo.argo_workflow_compiler import (
    ArgoWorkflowCompiler,
)
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.adapters.outbound.memory.content_cache import MemoryContentCache
from orchestrator.adapters.outbound.memory.index import DeliveryIndex
from orchestrator.adapters.outbound.memory.observation_store import (
    MemoryObservationStore,
)
from orchestrator.adapters.outbound.memory.studios_index import StudioStatusIndex
from orchestrator.adapters.outbound.memory.turns import TurnStore
from orchestrator.adapters.inbound.http.session import operator_authorization_revision
from orchestrator.application.ports.inbound.console import ConsoleCapabilities
from orchestrator.application.ports.inbound.projections.maintenance_state import (
    MaintenanceStatePort,
)
from orchestrator.application.ports.inbound.projections.refresh_metadata import (
    RefreshMetadataPort,
)
from orchestrator.application.ports.inbound.promotion.promotion_options import (
    PromotionOptionsPort,
)
from orchestrator.application.ports.inbound.promotion.promotion_state import (
    PromotionStatePort,
)
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.git_credential_check import (
    GitCredentialCheck,
)
from orchestrator.application.ports.outbound.maintenance_acts import MaintenanceActs
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.ports.outbound.repositories.repository_incarnations import (
    RepositoryIncarnations,
)
from orchestrator.application.ports.outbound.run_log_store import RunLogStore
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.worker_runner import WorkerRunner
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.identity.repository_incarnation import (
    RepositoryIncarnation,
)
from orchestrator.application.services.operations.delegated_grants import (
    DelegatedGrants,
)
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.settings.credential_resolver import (
    CredentialResolver,
)
from orchestrator.application.services.settings.held_credential import HeldCredential
from orchestrator.application.use_cases.content.maintenance_substance import (
    MaintenanceSubstance,
)
from orchestrator.application.use_cases.content.phase_substance import PhaseSubstance
from orchestrator.application.use_cases.content.repo_file import RepoFile
from orchestrator.application.use_cases.content.repo_tree import RepoTree
from orchestrator.application.use_cases.copilot.chat import Chat
from orchestrator.application.use_cases.copilot.chat_poll import ChatPoll
from orchestrator.application.use_cases.copilot.chat_start import ChatStart
from orchestrator.application.use_cases.copilot.fleet_chat import FleetChat
from orchestrator.application.use_cases.copilot.fleet_chat_start import FleetChatStart
from orchestrator.application.use_cases.delivery.advance import Advance
from orchestrator.application.use_cases.delivery.close_line import CloseLine
from orchestrator.application.use_cases.delivery.drive import Drive
from orchestrator.application.use_cases.delivery.establish import Establish
from orchestrator.application.use_cases.delivery.plan_next import PlanNext
from orchestrator.application.use_cases.delivery.reopen import Reopen
from orchestrator.application.use_cases.delivery.set_delivery_config import (
    SetDeliveryConfig,
)
from orchestrator.application.use_cases.delivery.sign_gate import SignGate
from orchestrator.application.use_cases.delivery.start import Start
from orchestrator.application.use_cases.maintenance.maintenance_close_ticket import (
    MaintenanceCloseTicket,
)
from orchestrator.application.use_cases.maintenance.maintenance_comment import (
    MaintenanceComment,
)
from orchestrator.application.use_cases.maintenance.maintenance_drive import (
    MaintenanceDrive,
)
from orchestrator.application.use_cases.maintenance.maintenance_merge import (
    MaintenanceMerge,
)
from orchestrator.application.use_cases.maintenance.maintenance_positions import (
    MaintenancePositions,
)
from orchestrator.application.use_cases.maintenance.maintenance_switch_to_delivery import (
    MaintenanceSwitchToDelivery,
)
from orchestrator.application.use_cases.maintenance.reconcile_maintenance_runs import (
    ReconcileMaintenanceRuns,
)
from orchestrator.application.use_cases.operations.inspect_operation import (
    InspectOperation,
)
from orchestrator.application.use_cases.operations.resolve_delegated_grant import (
    ResolveDelegatedGrant,
)
from orchestrator.application.use_cases.projections.collect_delivery_config import (
    CollectDeliveryConfig,
)
from orchestrator.application.use_cases.projections.collect_maintenance_state import (
    CollectMaintenanceState,
)
from orchestrator.application.use_cases.projections.collect_promotion_options import (
    CollectPromotionOptions,
)
from orchestrator.application.use_cases.projections.collect_promotion_state import (
    CollectPromotionState,
)
from orchestrator.application.use_cases.projections.delivery_overview import (
    DeliveryOverview,
)
from orchestrator.application.use_cases.projections.fleet import Fleet
from orchestrator.application.use_cases.projections.fleet_staleness import (
    FleetStaleness,
)
from orchestrator.application.use_cases.projections.list_deliveries import (
    ListDeliveries,
)
from orchestrator.application.use_cases.projections.maintenance_inbox import (
    MaintenanceInbox,
)
from orchestrator.application.use_cases.projections.maintenance_state import (
    MaintenanceState,
)
from orchestrator.application.use_cases.projections.refresh import Refresh
from orchestrator.application.use_cases.projections.refresh_metadata import (
    RefreshMetadata,
)
from orchestrator.application.use_cases.projections.snapshot_metadata import (
    SnapshotMetadata,
)
from orchestrator.application.use_cases.projections.status import Status
from orchestrator.application.use_cases.projections.studios import Studios
from orchestrator.application.use_cases.promotion.declare_promotion_target import (
    DeclarePromotionTarget,
)
from orchestrator.application.use_cases.promotion.instantiation import Instantiation
from orchestrator.application.use_cases.promotion.promotion_drive import PromotionDrive
from orchestrator.application.use_cases.promotion.promotion_options import (
    PromotionOptions,
)
from orchestrator.application.use_cases.promotion.promotion_state import PromotionState
from orchestrator.application.use_cases.runs.resume_run import ResumeRun
from orchestrator.application.use_cases.runs.run_graph import RunGraph
from orchestrator.application.use_cases.runs.run_logs import RunLogs
from orchestrator.application.use_cases.runs.run_retention import RunRetention
from orchestrator.application.use_cases.runs.run_status import RunStatus
from orchestrator.application.use_cases.runs.run_repository import RunRepository
from orchestrator.application.use_cases.runs.runs import Runs
from orchestrator.application.use_cases.runs.start_turn import StartTurn
from orchestrator.application.use_cases.runs.stop_run import StopRun
from orchestrator.application.use_cases.settings.apply_agent_to_delivery import (
    ApplyAgentToDelivery,
)
from orchestrator.application.use_cases.settings.apply_agent_to_driver import (
    ApplyAgentToDriver,
)
from orchestrator.application.use_cases.settings.console_identity_setting import (
    ConsoleIdentitySetting,
)
from orchestrator.application.use_cases.settings.delete_agent import DeleteAgent
from orchestrator.application.use_cases.settings.delete_git_identity import (
    DeleteGitIdentity,
)
from orchestrator.application.use_cases.settings.delete_pair_credential import (
    DeletePairCredential,
)
from orchestrator.application.use_cases.settings.delivery_config import DeliveryConfig
from orchestrator.application.use_cases.settings.driver_config import DriverConfig
from orchestrator.application.use_cases.settings.get_setting import GetSetting
from orchestrator.application.use_cases.settings.git_role_catalog import GitRoleCatalog
from orchestrator.application.use_cases.settings.git_roles import GitRoles
from orchestrator.application.use_cases.settings.list_agents import ListAgents
from orchestrator.application.use_cases.settings.list_git_identities import (
    ListGitIdentities,
)
from orchestrator.application.use_cases.settings.list_pair_credentials import (
    ListPairCredentials,
)
from orchestrator.application.use_cases.settings.mcp_doors import McpDoors
from orchestrator.application.use_cases.settings.pair_credential_held import (
    PairCredentialHeld,
)
from orchestrator.application.use_cases.settings.pair_credential_host import (
    PairCredentialHost,
)
from orchestrator.application.use_cases.settings.pair_credential_ref import (
    PairCredentialRef,
)
from orchestrator.application.use_cases.settings.pair_credential_secret import (
    PairCredentialSecret,
)
from orchestrator.application.use_cases.settings.set_agent import SetAgent
from orchestrator.application.use_cases.settings.set_delivery_model import (
    SetDeliveryModel,
)
from orchestrator.application.use_cases.settings.set_delivery_timeout import (
    SetDeliveryTimeout,
)
from orchestrator.application.use_cases.settings.set_driver_config import (
    SetDriverConfig,
)
from orchestrator.application.use_cases.settings.set_git_identity import SetGitIdentity
from orchestrator.application.use_cases.settings.set_git_roles import SetGitRoles
from orchestrator.application.use_cases.settings.set_pair_credential import (
    SetPairCredential,
)
from orchestrator.application.use_cases.settings.set_setting import SetSetting
from orchestrator.application.use_cases.settings.set_team import SetTeam
from orchestrator.application.use_cases.settings.delete_team import DeleteTeam
from orchestrator.application.use_cases.settings.assign_project import AssignProject
from orchestrator.application.use_cases.settings.list_teams import ListTeams
from orchestrator.application.services.settings.team_roster_store import (
    TeamRosterStore,
)
from orchestrator.application.use_cases.settings.set_target_selection import (
    SetTargetSelection,
)
from orchestrator.application.use_cases.studios.pause_app import PauseApp
from orchestrator.application.use_cases.studios.resume_app import ResumeApp
from orchestrator.application.use_cases.studios.tool_urls import ToolUrls
from orchestrator.domain.fleet import DEFAULT_PLATFORM_REPO

_Capability = TypeVar("_Capability")


def _check(instance: _Capability, port: type) -> _Capability:
    """Refuse a capability that does not satisfy the port it is wired as."""
    if not isinstance(instance, port):
        raise TypeError(f"{type(instance).__name__} does not satisfy {port.__name__}")
    return instance


def _verified(capabilities: ConsoleCapabilities) -> ConsoleCapabilities:
    """Refuse an assembly in which any published capability misses its port."""
    ports = get_type_hints(ConsoleCapabilities)
    for field in fields(capabilities):
        _check(getattr(capabilities, field.name), ports[field.name])
    return capabilities


def build_capabilities(
    repos: RepoStore,
    runner: WorkerRunner | None = None,
    workflows: WorkflowRunner | None = None,
    credentials: CredentialStore | None = None,
    config: ConfigStore | None = None,
    index: DeliveryIndex | None = None,
    source: DeliverySource | None = None,
    studios: StudioGateway | None = None,
    studio_index: StudioStatusIndex | None = None,
    driver=None,
    msource: MaintenanceSource | None = None,
    psource=None,
    door=None,
    macts: MaintenanceActs | None = None,
    gitcheck: GitCredentialCheck | None = None,
    run_log_store: RunLogStore | None = None,
    worker_image: str = "",
    platform_repo: str = DEFAULT_PLATFORM_REPO,
    events: EventPublisher | None = None,
    console_credential: HeldCredential | None = None,
    *,
    admission: OperationAdmission | None = None,
    incarnations: RepositoryIncarnations | None = None,
    background_scope=None,
    public_domain: str = "",
) -> ConsoleCapabilities:
    incarnations = incarnations or RepositoryIncarnation(repos, config, credentials)
    compiler = ArgoWorkflowCompiler(public_domain=public_domain)
    admission = admission or OperationAdmission(
        OperationReceiptStore(os.environ.get("FC_ARCHIVE_DIR", "/data/archive"))
    )
    observations = MemoryObservationStore()
    turns = TurnStore()
    index = index or DeliveryIndex()
    studio_index = studio_index or StudioStatusIndex()
    content_cache = MemoryContentCache()

    # Capabilities over published observations, settings and stores alone.
    uc_status = Status(index=index)
    uc_list_deliveries = ListDeliveries(index=index)
    uc_fleet = Fleet(observations=observations)
    uc_fleet_staleness = FleetStaleness(observations=observations)
    uc_studios = Studios(studio_index=studio_index)
    uc_pause_app = PauseApp(studios=studios, admission=admission)
    uc_resume_app = ResumeApp(studios=studios, admission=admission)
    uc_delivery_config = DeliveryConfig(
        observations=observations, config=config, credentials=credentials
    )
    uc_set_target_selection = SetTargetSelection(
        config=config, incarnations=incarnations, admission=admission
    )
    uc_repo_tree = RepoTree(source=source, index=index, cache=content_cache)
    uc_repo_file = RepoFile(source=source, index=index, cache=content_cache)
    uc_chat_poll = ChatPoll(turns=turns)
    uc_start_turn = StartTurn(turns=turns)
    uc_runs = Runs(observations=observations)
    uc_run_graph = RunGraph(observations=observations)
    uc_stop_run = StopRun(workflows=workflows, admission=admission)
    uc_resume_run = ResumeRun(source=source, workflows=workflows, admission=admission)
    uc_run_logs = RunLogs(run_log_store=run_log_store, workflows=workflows)
    uc_run_status = RunStatus(observations=observations)
    uc_run_repository = RunRepository(observations=observations, workflows=workflows)
    uc_driver_config = DriverConfig(config=config)
    uc_promotion_state = PromotionState(observations=observations)
    uc_promotion_options = PromotionOptions(observations=observations)
    uc_instantiation = Instantiation(psource=psource)
    uc_maintenance_state = MaintenanceState(observations=observations)
    uc_maintenance_inbox = MaintenanceInbox(observations=observations)
    uc_maintenance_comment = MaintenanceComment(macts=macts, admission=admission)
    uc_maintenance_close_ticket = MaintenanceCloseTicket(
        events=events, macts=macts, admission=admission
    )
    uc_maintenance_switch_to_delivery = MaintenanceSwitchToDelivery(
        macts=macts, msource=msource, admission=admission
    )
    uc_git_role_catalog = GitRoleCatalog()
    uc_list_git_identities = ListGitIdentities(config=config)
    uc_set_git_identity = SetGitIdentity(
        config=config,
        console_credential=console_credential,
        gitcheck=gitcheck,
        admission=admission,
    )
    uc_delete_git_identity = DeleteGitIdentity(
        config=config, console_credential=console_credential, admission=admission
    )
    uc_git_roles = GitRoles(config=config)
    uc_tool_urls = ToolUrls(studios=studios)
    uc_list_pair_credentials = ListPairCredentials(config=config)
    uc_delete_pair_credential = DeletePairCredential(config=config, admission=admission)
    uc_pair_credential_held = PairCredentialHeld(config=config)
    uc_pair_credential_secret = PairCredentialSecret(config=config)
    uc_pair_credential_host = PairCredentialHost(config=config)
    team_roster = TeamRosterStore(config)
    uc_list_teams = ListTeams(cap_team_roster=team_roster)
    uc_set_team = SetTeam(teams=team_roster, admission=admission)
    uc_delete_team = DeleteTeam(teams=team_roster, admission=admission)
    uc_assign_project = AssignProject(teams=team_roster, admission=admission)
    uc_list_agents = ListAgents(config=config)
    uc_set_agent = SetAgent(
        config=config, driver=driver, cap_team_roster=team_roster, admission=admission
    )
    uc_delete_agent = DeleteAgent(config=config, admission=admission)
    uc_mcp_doors = McpDoors()
    uc_get_setting = GetSetting(config=config)
    uc_set_setting = SetSetting(config=config, admission=admission)

    # Current delivery configuration: commands read the committed line, never the
    # observed projection.
    current_delivery_config = _check(
        CollectDeliveryConfig(config=config, credentials=credentials, source=source),
        DeliveryConfigPort,
    )

    uc_run_retention = RunRetention(cap_get_setting=uc_get_setting)
    uc_set_driver_config = SetDriverConfig(
        config=config, cap_driver_config=uc_driver_config, admission=admission
    )
    uc_apply_agent_to_driver = ApplyAgentToDriver(
        config=config, cap_driver_config=uc_driver_config, admission=admission
    )
    uc_set_git_roles = SetGitRoles(
        config=config,
        console_credential=console_credential,
        cap_git_roles=uc_git_roles,
        admission=admission,
    )
    uc_console_identity_setting = ConsoleIdentitySetting(
        config=config, cap_git_roles=uc_git_roles
    )
    uc_set_pair_credential = SetPairCredential(
        config=config, cap_pair_credential_held=uc_pair_credential_held, admission=admission
    )
    uc_pair_credential_ref = PairCredentialRef(
        cap_pair_credential_held=uc_pair_credential_held
    )
    uc_maintenance_positions = MaintenancePositions(
        observations=observations,
        door=door,
        msource=msource,
        psource=psource,
        cap_git_roles=uc_git_roles,
        cap_instantiation=uc_instantiation,
        cap_list_git_identities=uc_list_git_identities,
    )
    uc_maintenance_substance = MaintenanceSubstance(
        observations=observations,
        msource=msource,
        workflows=workflows,
        cap_git_roles=uc_git_roles,
        cap_list_git_identities=uc_list_git_identities,
    )
    uc_maintenance_merge = MaintenanceMerge(
        msource=msource,
        cap_git_roles=uc_git_roles,
        cap_list_git_identities=uc_list_git_identities,
        events=events,
        macts=macts,
        psource=psource,
        cap_instantiation=uc_instantiation,
        admission=admission,
    )
    uc_fleet_chat = FleetChat(
        config=config, driver=driver, cap_fleet=uc_fleet, cap_studios=uc_studios
    )
    uc_fleet_chat_start = FleetChatStart(turns=turns, cap_fleet_chat=uc_fleet_chat)
    uc_delivery_overview = DeliveryOverview(
        studio_index=studio_index,
        cap_delivery_config=uc_delivery_config,
        cap_status=uc_status,
    )
    uc_phase_substance = PhaseSubstance(
        studios=studios, cap_repo_file=uc_repo_file, cap_status=uc_status
    )
    uc_chat = Chat(
        config=config,
        credentials=credentials,
        driver=driver,
        workflows=workflows,
        cap_delivery_config=uc_delivery_config,
        cap_maintenance_positions=uc_maintenance_positions,
        cap_repo_file=uc_repo_file,
        cap_status=uc_status,
    )
    uc_chat_start = ChatStart(turns=turns, cap_chat=uc_chat)
    uc_reopen = Reopen(
        events=events,
        index=index,
        repos=repos,
        source=source,
        cap_status=uc_status,
        admission=admission,
    )
    uc_sign_gate = SignGate(
        events=events,
        index=index,
        repos=repos,
        source=source,
        workflows=workflows,
        cap_status=uc_status,
        admission=admission,
    )
    uc_set_delivery_config = SetDeliveryConfig(
        repos=repos,
        source=source,
        cap_delivery_config=current_delivery_config,
        admission=admission,
        observations=observations,
    )
    uc_set_delivery_model = SetDeliveryModel(
        credentials=credentials,
        driver=driver,
        cap_delivery_config=current_delivery_config,
        cap_set_target_selection=uc_set_target_selection,
        admission=admission,
    )
    uc_set_delivery_timeout = SetDeliveryTimeout(
        cap_delivery_config=current_delivery_config,
        cap_set_target_selection=uc_set_target_selection,
        admission=admission,
    )
    uc_apply_agent_to_delivery = ApplyAgentToDelivery(
        config=config,
        credentials=credentials,
        cap_delivery_config=current_delivery_config,
        cap_set_target_selection=uc_set_target_selection,
        admission=admission,
    )
    uc_plan_next = PlanNext(
        credentials=credentials,
        cap_delivery_config=current_delivery_config,
        cap_status=uc_status,
    )
    uc_establish = Establish(
        events=events,
        repos=repos,
        run_log_store=run_log_store,
        source=source,
        studios=studios,
        workflows=workflows,
        cap_run_retention=uc_run_retention,
        admission=admission,
        incarnations=incarnations,
        index=index,
        worker_image=worker_image,
        teams=team_roster,
    )
    uc_start = Start(
        cap_establish=uc_establish,
        cap_plan_next=uc_plan_next,
        admission=admission,
    )
    uc_close_line = CloseLine(
        events=events,
        index=index,
        repos=repos,
        run_log_store=run_log_store,
        source=source,
        workflows=workflows,
        cap_run_retention=uc_run_retention,
        cap_status=uc_status,
        admission=admission,
    )
    uc_advance = Advance(
        runner=runner,
        cap_delivery_config=current_delivery_config,
        cap_plan_next=uc_plan_next,
        admission=admission,
    )
    uc_drive = Drive(
        config=config,
        credentials=credentials,
        events=events,
        psource=psource,
        repos=repos,
        source=source,
        studios=studios,
        worker_image=worker_image,
        workflows=workflows,
        cap_git_roles=uc_git_roles,
        cap_instantiation=uc_instantiation,
        cap_pair_credential_held=uc_pair_credential_held,
        cap_run_retention=uc_run_retention,
        cap_status=uc_status,
        cap_tool_urls=uc_tool_urls,
        admission=admission,
        compiler=compiler,
        incarnations=incarnations,
    )
    uc_promotion_drive = PromotionDrive(
        config=config,
        credentials=credentials,
        msource=msource,
        psource=psource,
        studios=studios,
        worker_image=worker_image,
        workflows=workflows,
        cap_git_roles=uc_git_roles,
        cap_pair_credential_held=uc_pair_credential_held,
        cap_run_retention=uc_run_retention,
        admission=admission,
        compiler=compiler,
        incarnations=incarnations,
    )
    uc_maintenance_drive = MaintenanceDrive(
        observations=observations,
        config=config,
        credentials=credentials,
        door=door,
        events=events,
        msource=msource,
        psource=psource,
        studios=studios,
        worker_image=worker_image,
        workflows=workflows,
        cap_git_roles=uc_git_roles,
        cap_instantiation=uc_instantiation,
        cap_list_git_identities=uc_list_git_identities,
        cap_pair_credential_held=uc_pair_credential_held,
        cap_run_retention=uc_run_retention,
        admission=admission,
        compiler=compiler,
        incarnations=incarnations,
    )

    # Source collectors: the background observation and current command evidence.
    current_promotion_state = _check(
        CollectPromotionState(
            config=config,
            door=door,
            msource=msource,
            psource=psource,
            cap_pair_credential_held=uc_pair_credential_held,
        ),
        PromotionStatePort,
    )
    uc_declare_promotion_target = DeclarePromotionTarget(
        psource=psource,
        cap_promotion_state=current_promotion_state,
        observations=observations,
        admission=admission,
    )
    refresh_metadata = _check(
        RefreshMetadata(
            observations=observations,
            maintenance=_check(
                CollectMaintenanceState(
                    observations=observations,
                    psource=psource,
                    cap_instantiation=uc_instantiation,
                    cap_maintenance_positions=uc_maintenance_positions,
                    cap_status=uc_status,
                ),
                MaintenanceStatePort,
            ),
            promotion=current_promotion_state,
            options=_check(CollectPromotionOptions(psource=psource), PromotionOptionsPort),
            config=current_delivery_config,
        ),
        RefreshMetadataPort,
    )
    uc_refresh = Refresh(
        observations=observations,
        events=events,
        index=index,
        msource=msource,
        platform_repo=platform_repo,
        run_log_store=run_log_store,
        source=source,
        studio_index=studio_index,
        studios=studios,
        workflows=workflows,
        cap_list_deliveries=uc_list_deliveries,
        cap_run_graph=uc_run_graph,
        cap_run_retention=uc_run_retention,
        cap_refresh_metadata=refresh_metadata,
        **(
            {"background_scope": background_scope}
            if background_scope is not None
            else {}
        ),
    )
    current_authorization_revision = operator_authorization_revision()
    return _verified(
        ConsoleCapabilities(
            status=uc_status,
            list_deliveries=uc_list_deliveries,
            refresh=uc_refresh,
            fleet=uc_fleet,
            fleet_staleness=uc_fleet_staleness,
            studios=uc_studios,
            pause_app=uc_pause_app,
            resume_app=uc_resume_app,
            delivery_overview=uc_delivery_overview,
            delivery_config=uc_delivery_config,
            set_target_selection=uc_set_target_selection,
            set_delivery_config=uc_set_delivery_config,
            set_delivery_model=uc_set_delivery_model,
            set_delivery_timeout=uc_set_delivery_timeout,
            reopen=uc_reopen,
            phase_substance=uc_phase_substance,
            repo_tree=uc_repo_tree,
            repo_file=uc_repo_file,
            chat=uc_chat,
            fleet_chat=uc_fleet_chat,
            chat_start=uc_chat_start,
            fleet_chat_start=uc_fleet_chat_start,
            chat_poll=uc_chat_poll,
            start_turn=uc_start_turn,
            plan_next=uc_plan_next,
            start=uc_start,
            establish=uc_establish,
            close_line=uc_close_line,
            advance=uc_advance,
            drive=uc_drive,
            runs=uc_runs,
            run_retention=uc_run_retention,
            run_graph=uc_run_graph,
            stop_run=uc_stop_run,
            resume_run=uc_resume_run,
            run_logs=uc_run_logs,
            run_status=uc_run_status,
            run_repository=uc_run_repository,
            sign_gate=uc_sign_gate,
            driver_config=uc_driver_config,
            set_driver_config=uc_set_driver_config,
            maintenance_positions=uc_maintenance_positions,
            promotion_state=uc_promotion_state,
            promotion_options=uc_promotion_options,
            declare_promotion_target=uc_declare_promotion_target,
            instantiation=uc_instantiation,
            promotion_drive=uc_promotion_drive,
            maintenance_state=uc_maintenance_state,
            maintenance_substance=uc_maintenance_substance,
            maintenance_inbox=uc_maintenance_inbox,
            maintenance_drive=uc_maintenance_drive,
            maintenance_merge=uc_maintenance_merge,
            maintenance_comment=uc_maintenance_comment,
            maintenance_close_ticket=uc_maintenance_close_ticket,
            maintenance_switch_to_delivery=uc_maintenance_switch_to_delivery,
            git_role_catalog=uc_git_role_catalog,
            list_git_identities=uc_list_git_identities,
            set_git_identity=uc_set_git_identity,
            delete_git_identity=uc_delete_git_identity,
            git_roles=uc_git_roles,
            set_git_roles=uc_set_git_roles,
            tool_urls=uc_tool_urls,
            console_identity_setting=uc_console_identity_setting,
            list_pair_credentials=uc_list_pair_credentials,
            set_pair_credential=uc_set_pair_credential,
            delete_pair_credential=uc_delete_pair_credential,
            pair_credential_held=uc_pair_credential_held,
            pair_credential_secret=uc_pair_credential_secret,
            pair_credential_host=uc_pair_credential_host,
            pair_credential_ref=uc_pair_credential_ref,
            list_agents=uc_list_agents,
            set_agent=uc_set_agent,
            delete_agent=uc_delete_agent,
            apply_agent_to_driver=uc_apply_agent_to_driver,
            apply_agent_to_delivery=uc_apply_agent_to_delivery,
            mcp_doors=uc_mcp_doors,
            get_setting=uc_get_setting,
            set_setting=uc_set_setting,
            team_roster=team_roster,
            list_teams=uc_list_teams,
            set_team=uc_set_team,
            delete_team=uc_delete_team,
            assign_project=uc_assign_project,
            snapshot_metadata=SnapshotMetadata(observations),
            reconcile_maintenance_runs=ReconcileMaintenanceRuns(
                cap_maintenance_merge=uc_maintenance_merge,
                observations=observations,
                config=config,
                credentials=credentials,
                door=door,
                events=events,
                msource=msource,
                psource=psource,
                studios=studios,
                worker_image=worker_image,
                workflows=workflows,
                cap_delivery_config=current_delivery_config,
                cap_git_roles=uc_git_roles,
                cap_instantiation=uc_instantiation,
                cap_list_git_identities=uc_list_git_identities,
                cap_pair_credential_held=uc_pair_credential_held,
                cap_run_graph=uc_run_graph,
                cap_run_retention=uc_run_retention,
                compiler=compiler,
                admission=admission,
                authorization_revision=current_authorization_revision,
            ),
            inspect_operation=InspectOperation(admission),
            resolve_delegated_grant=ResolveDelegatedGrant(
                DelegatedGrants(admission.receipts, current_authorization_revision)
            ),
        )
    )

import os

from orchestrator.adapters.outbound.agents.claude_worker_runner import (
    ClaudeWorkerRunner,
)
from orchestrator.adapters.outbound.agents.http_driver_agent import HttpDriverAgent
from orchestrator.adapters.outbound.archives.file_run_log_store import FileRunLogStore
from orchestrator.adapters.outbound.argo.argo_workflow_runner import ArgoWorkflowRunner
from orchestrator.adapters.outbound.credentials.k8s_credential_store import (
    K8sCredentialStore,
)
from orchestrator.adapters.outbound.events.resolve_event_publisher import (
    resolve_event_publisher,
)
from orchestrator.adapters.outbound.github.github_acts import GitHubActs
from orchestrator.adapters.outbound.github.github_delivery_source import (
    GitHubDeliverySource,
)
from orchestrator.adapters.outbound.github.github_door import GitHubDoor
from orchestrator.adapters.outbound.github.github_maintenance_source import (
    GitHubMaintenanceSource,
)
from orchestrator.adapters.outbound.github.github_promotion_source import (
    GithubPromotionSource,
)
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from orchestrator.adapters.outbound.repositories.host_selected_door import (
    HostSelectedDoor,
)
from orchestrator.adapters.outbound.settings.k8s_config_store import K8sConfigStore
from orchestrator.adapters.outbound.studios.http_studio_gateway import HttpStudioGateway
from orchestrator.domain.fleet import DEFAULT_PLATFORM_REPO


def _require_install_value(key: str) -> str:
    """An install-supplied value with NO fallback: read here at start, or fail loud naming
    the key. A default equal to one install's value is the config-default anti-pattern
    (REF-AppContract section 1): a console misconfigured for a different organization would
    run wrongly against the wrong org's issues, PRs, and registry instead of refusing to
    start. Every install derives its GitHub owner and its worker image from install facts (the
    platform chart and the shared CI do the same), so the console reads them the same way and
    carries no baked-in owner. This is the composition root's single read point; the value is
    threaded to whoever needs it rather than re-read (or re-defaulted) elsewhere."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(
            f"{key} is required and unset: set it per-install (there is no default). The console reads its GitHub owner and worker image from install config."
        )
    return value


def build_service() -> ConsoleCapabilities:
    config = K8sConfigStore()
    org = _require_install_value("FC_ORG")
    worker_image = _require_install_value("FC_WORKER_IMAGE")
    public_domain = os.environ.get("FC_DOMAIN", "").strip()
    platform_repo = (
        os.environ.get("FC_PLATFORM_REPO", "").strip() or DEFAULT_PLATFORM_REPO
    )
    resolver = CredentialResolver(config)
    console_credential = HeldCredential(resolver.console_token)
    token = console_credential.get
    transport = GitHubTransport()
    door = HostSelectedDoor(
        {"github.com": GitHubDoor(resolver.pair_token, transport=transport)},
        resolver.pair_host,
    )
    acts = GitHubActs(org, token, transport=transport)
    return build_capabilities(
        GitHubRepoStore(org, token, transport=transport),
        ClaudeWorkerRunner(),
        ArgoWorkflowRunner(),
        K8sCredentialStore(),
        config,
        index=DeliveryIndex(),
        platform_repo=platform_repo,
        source=GitHubDeliverySource(org, token, transport=transport),
        studios=HttpStudioGateway(config),
        studio_index=StudioStatusIndex(),
        driver=HttpDriverAgent(),
        msource=GitHubMaintenanceSource(org, token, transport=transport),
        psource=GithubPromotionSource(org, token, transport=transport),
        door=door,
        macts=acts,
        gitcheck=acts,
        run_log_store=FileRunLogStore(),
        worker_image=worker_image,
        public_domain=public_domain,
        console_credential=console_credential,
        events=resolve_event_publisher(),
        background_scope=transport.background_scope,
    )


from orchestrator.application.ports.inbound.projections.read_local_delivery import (
    ReadLocalDeliveryPort,
)


def build_local_reader() -> ReadLocalDeliveryPort:
    from orchestrator.adapters.outbound.filesystem.local_delivery_source import (
        LocalDeliverySource,
    )
    from orchestrator.application.use_cases.projections.read_local_delivery import (
        ReadLocalDelivery,
    )

    return ReadLocalDelivery(LocalDeliverySource("."))
