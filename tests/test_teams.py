"""Teams on one install: admission from the identity provider's groups, reads scoped to the
caller's teams, the team a new line belongs to, and the owner levels of saved agents
(INT-FC-R183 to INT-FC-R189)."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from capability_support import TestRepositoryIncarnations, UnitCredentials, make_capabilities
from fastapi.testclient import TestClient
from pytest_intent import intent
from starlette.requests import Request

from orchestrator.adapters.inbound.http.app import create_app
from orchestrator.adapters.inbound.http.session import (
    EXECUTION_ACTIONS,
    command_context,
    operator_authorization_revision,
)
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.application.ports.inbound.command_actions import (
    ADMIN_ACTIONS,
    COMMAND_ACTIONS,
)
from orchestrator.application.services.runs.prepare_config import prepare_config
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.seat_refused import SeatRefused
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.fleet_item import FleetItem
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.services.agent_access import refuse_foreign_seat

ISSUER = "https://identity.example/app-realm"
PROXY = {"X-Console-Proxy-Secret": "trusted-proxy"}


def user(subject: str, *groups: str) -> dict[str, str]:
    return {
        **PROXY,
        "X-Auth-Request-User": subject,
        "X-Auth-Request-Email": f"{subject}@example.org",
        "X-Auth-Request-Groups": ",".join(groups),
    }


ADMIN = user("root", "/console-admins")
ALICE = user("alice", "/team-alpha")
BOB = user("bob", "team-alpha")
CAROL = user("carol", "team-beta")


def keyed(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": uuid4().hex}


def context(
    principal: str,
    *,
    teams: tuple[str, ...] = (),
    repositories: tuple[str, ...] = (),
    admin: bool = False,
    kind: str = "operator",
) -> CommandContext:
    if kind == "machine":
        actions = EXECUTION_ACTIONS
    else:
        actions = frozenset(COMMAND_ACTIONS.values()) - (frozenset() if admin else ADMIN_ACTIONS)
    return CommandContext(
        principal,
        kind,
        "unit-grant",
        actions,
        frozenset({"org/*"}) if admin else frozenset(repositories),
        "unit-authorization",
        "org",
        teams=frozenset(teams),
        admin=admin,
        principal_label=principal.rsplit("#", 1)[-1] + "@example.org",
        claimable=frozenset() if admin or kind == "machine" else frozenset({"org/*"}),
    )


def kwargs(caller: CommandContext) -> dict:
    return {"context": caller, "operation_id": uuid4().hex}


ROOT = context(ISSUER + "#root", admin=True)
ALICE_CTX = context(ISSUER + "#alice", teams=("alpha",), repositories=("org/alpha-shop",))
BOB_CTX = context(ISSUER + "#bob", teams=("alpha",), repositories=("org/alpha-shop",))
CAROL_CTX = context(ISSUER + "#carol", teams=("beta",), repositories=("org/beta-bank",))
DAVE_CTX = context(
    ISSUER + "#dave", teams=("alpha", "beta"), repositories=("org/alpha-shop", "org/beta-bank")
)
MACHINE = context("execution#bench", kind="machine", repositories=("org/*",))


class Repos:
    """A repository store holding the names in ``holding``; any other name is new."""

    def __init__(self, holding=()):
        self.holding = set(holding)
        self.ensured: list[str] = []

    def list_delivery_repos(self):
        return []

    def repo_exists(self, target):
        return target.split("/")[-1] in self.holding

    def ensure(self, target):
        self.ensured.append(target)
        return "org/" + target.split("/")[-1]

    def register(self, workspace, request="", source=(), source_name=""):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        pass


class Credentials(UnitCredentials):
    def get_delivery(self, slug):
        return self.values.get(slug, "")


class Driver:
    def __init__(self):
        self.systems: list[str] = []

    def chat(self, system, messages, *, credential, model, base_url):
        self.systems.append(system)
        return "noted"

    def validate(self, credential, *, model, base_url):
        return True


class World:
    """The capabilities beside the stores the tests seed and read."""

    def __init__(self, capabilities, config, driver):
        self.capabilities, self.config, self.driver = capabilities, config, driver

    def __getattr__(self, name):
        return getattr(self.capabilities, name)


def item(repo: str) -> FleetItem:
    return FleetItem(repo, repo.split("/")[-1], False, None, None, False, None, None)


@pytest.fixture
def teams_env(monkeypatch):
    monkeypatch.setenv("FC_OIDC_ENABLED", "true")
    monkeypatch.setenv("FC_ORG", "org")
    monkeypatch.setenv("FC_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("FC_PROXY_SECRET", "trusted-proxy")
    monkeypatch.setenv("FC_ADMIN_GROUP", "console-admins")
    monkeypatch.delenv("FC_REPOSITORIES", raising=False)


@pytest.fixture
def service():
    """Two teams, a project each, and one project assigned to none."""
    config = InMemoryConfigStore()
    driver = Driver()
    svc = make_capabilities(Repos(), config=config, credentials=Credentials(), driver=driver)
    svc.set_team.execute("alpha", "/team-alpha", **kwargs(ROOT))
    svc.set_team.execute("beta", "team-beta", **kwargs(ROOT))
    svc.assign_project.execute("org/alpha-shop", "alpha", **kwargs(ROOT))
    svc.assign_project.execute("org/beta-bank", "beta", **kwargs(ROOT))
    observations = svc.fleet.observations
    observations.fleet = [item("org/Alpha-Shop"), item("org/beta-bank"), item("org/loose-ends")]
    observations.inbox = [{"repo": "org/alpha-shop"}, {"repo": "org/beta-bank"}, {"repo": "org/loose-ends"}]
    observations.runs = [
        RunInventoryEntry("live:workflow.argoproj.io/r-a", "r-a", "Running", repository="org/Alpha-Shop"),
        RunInventoryEntry("live:workflow.argoproj.io/r-b", "r-b", "Running", repository="org/beta-bank"),
        RunInventoryEntry("live:workflow.argoproj.io/r-x", "r-x", "Running"),
    ]
    for repo in ("org/alpha-shop", "org/beta-bank", "org/loose-ends"):
        svc.list_deliveries.index.put(replace(derive_state(repo), repo=repo))
    return World(svc, config, driver)


@pytest.fixture
def client(teams_env, service):
    return TestClient(create_app(service.capabilities))


def edge(headers: dict[str, str], app=None, method: str = "GET", path: str = "/api/fleet") -> Request:
    scope = {
        "type": "http", "method": method, "path": path, "query_string": b"",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
    }
    if app is not None:
        scope["app"] = app
    return Request(scope)


# INT-FC-R183: admission resolves admin standing and teams from the forwarded groups.

@intent("INT-FC-R183")
def test_an_admin_group_member_holds_every_act_on_the_installation(teams_env, service):
    app = create_app(service.capabilities)
    caller = command_context(edge(ADMIN, app))
    assert caller.admin and caller.allowed_actions == frozenset(COMMAND_ACTIONS.values())
    assert caller.repositories == frozenset({"org/*"})
    caller.authorize("settings.team")
    caller.authorize("delivery.drive", "org/loose-ends")


@intent("INT-FC-R183")
def test_a_team_member_holds_its_teams_projects_and_no_team_settings(teams_env, service):
    app = create_app(service.capabilities)
    alice = command_context(edge(ALICE, app))
    assert not alice.admin and alice.teams == frozenset({"alpha"})
    assert alice.repositories == frozenset({"org/alpha-shop"})
    assert alice.allowed_actions == frozenset(COMMAND_ACTIONS.values()) - ADMIN_ACTIONS
    alice.authorize("delivery.drive", "org/Alpha-Shop")
    for repository in ("org/beta-bank", "org/loose-ends"):
        with pytest.raises(PermissionDenied):
            alice.authorize("delivery.drive", repository)
    for action in sorted(ADMIN_ACTIONS):
        with pytest.raises(PermissionDenied):
            alice.authorize(action, "org/alpha-shop")
    # A group is named with or without its leading path slash.
    assert command_context(edge(BOB, app)).teams == frozenset({"alpha"})
    assert command_context(edge(user("eve"), app)).repositories == frozenset()


@intent("INT-FC-R183")
def test_with_no_admin_group_every_operator_is_an_admin(teams_env, service, monkeypatch):
    monkeypatch.delenv("FC_ADMIN_GROUP")
    caller = command_context(edge(CAROL, create_app(service.capabilities)))
    assert caller.admin and caller.repositories == frozenset({"org/*"})


@intent("INT-FC-R183")
def test_the_admin_group_is_part_of_the_admission_policy(teams_env, monkeypatch):
    before = operator_authorization_revision()
    monkeypatch.setenv("FC_ADMIN_GROUP", "other-admins")
    assert operator_authorization_revision() != before


@intent("INT-FC-R183")
def test_the_team_settings_are_an_admins_alone(client):
    assert client.get("/api/config/teams", headers=ALICE).status_code == 403
    teams = client.get("/api/config/teams", headers=ADMIN).json()["teams"]
    assert [(t["name"], t["group"], t["repositories"]) for t in teams] == [
        ("alpha", "team-alpha", ["org/alpha-shop"]),
        ("beta", "team-beta", ["org/beta-bank"]),
    ]
    assert client.post("/api/config/teams", json={"name": "gamma", "group": "g"}, headers=keyed(ALICE)).status_code == 403
    assert client.post("/api/config/team-projects", json={"repository": "org/alpha-shop", "team": "beta"}, headers=keyed(ALICE)).status_code == 403
    assert client.delete("/api/config/teams/beta", headers=keyed(ALICE)).status_code == 403
    assert client.post("/api/config/teams", json={"name": "gamma", "group": "/team-gamma"}, headers=keyed(ADMIN)).json() == {"name": "gamma", "group": "team-gamma"}
    assert client.post("/api/config/teams", json={"name": "delta", "group": "team-gamma"}, headers=keyed(ADMIN)).status_code == 422
    assert client.post("/api/config/team-projects", json={"repository": "org/loose-ends", "team": "nobody"}, headers=keyed(ADMIN)).status_code == 422


@intent("INT-FC-R183")
def test_the_session_read_names_the_callers_standing(client):
    assert client.get("/api/config/session", headers=ALICE).json() == {
        "oidc_enabled": True, "sign_out_url": "/oauth2/sign_out", "teams_enabled": True,
        "admin": False, "teams": ["alpha"], "user": "alice@example.org",
    }
    assert client.get("/api/config/session", headers=ADMIN).json()["admin"] is True


@intent("INT-FC-R183")
def test_deleting_a_team_unassigns_its_projects(service):
    service.delete_team.execute("beta", **kwargs(ROOT))
    roster = service.team_roster.execute()
    assert roster.team("beta") is None and roster.team_of("org/beta-bank") == ""


@intent("INT-FC-R183")
def test_an_unreadable_roster_answers_unavailable_not_an_open_door(teams_env):
    class Broken(InMemoryConfigStore):
        def list_settings(self, prefix):
            raise SourceUnavailable("settings store is down")

    client = TestClient(create_app(make_capabilities(Repos(), config=Broken())))
    response = client.get("/api/fleet", headers=ALICE)
    assert response.status_code == 503 and response.json()["code"] == "source_unavailable"


# INT-FC-R184: every read is the caller's teams' projects alone.

@intent("INT-FC-R184")
def test_the_fleet_deliveries_and_runs_are_the_callers_teams_alone(client):
    def repos(path, key, field, headers):
        return sorted(row.get(field) or "" for row in client.get(path, headers=headers).json()[key])

    assert repos("/api/fleet", "projects", "repo", ALICE) == ["org/Alpha-Shop"]
    assert repos("/api/fleet", "projects", "repo", CAROL) == ["org/beta-bank"]
    assert repos("/api/fleet", "projects", "repo", ADMIN) == ["org/Alpha-Shop", "org/beta-bank", "org/loose-ends"]
    assert repos("/api/deliveries", "deliveries", "repo", ALICE) == ["org/alpha-shop"]
    assert repos("/api/deliveries", "deliveries", "repo", ADMIN) == ["org/alpha-shop", "org/beta-bank", "org/loose-ends"]
    assert repos("/api/runs", "runs", "repo", ALICE) == ["org/Alpha-Shop"]
    assert repos("/api/runs", "runs", "repo", ADMIN) == ["", "org/Alpha-Shop", "org/beta-bank"]


@intent("INT-FC-R184")
def test_the_inbox_is_the_callers_teams_alone(service):
    assert [it["repo"] for it in service.maintenance_inbox.execute(viewer=ALICE_CTX)["items"]] == ["org/alpha-shop"]
    assert len(service.maintenance_inbox.execute(viewer=ROOT)["items"]) == 3


@intent("INT-FC-R184")
def test_a_read_naming_another_teams_repository_or_run_is_refused(client):
    for path in (
        "/api/deliveries/state?repo=org/beta-bank",
        "/api/deliveries/overview?repo=org/beta-bank",
        "/api/deliveries/config?repo=beta-bank",
        "/api/deliveries/tree?repo=org/beta-bank",
        "/api/deliveries/file?repo=org/beta-bank&path=README.md",
        "/api/maintenance/state?repo=org/loose-ends",
        "/api/promotion/state?repo=https://github.com/org/beta-bank",
        "/api/runs/status?handle=live:workflow.argoproj.io/r-b",
        "/api/runs/logs?handle=live:workflow.argoproj.io/r-b",
        "/api/runs/graph?handle=live:workflow.argoproj.io/r-x",
    ):
        assert client.get(path, headers=ALICE).status_code == 403, path
    assert client.get("/api/runs/status?handle=live:workflow.argoproj.io/r-a", headers=ALICE).status_code == 200
    assert client.get("/api/runs/status?handle=live:workflow.argoproj.io/r-b", headers=ADMIN).status_code == 200
    for path, body in (
        ("/api/deliveries/chat", {"target": "org/beta-bank", "message": "status?"}),
        ("/api/deliveries/plan", {"target": "org/beta-bank", "config": {"worker_credential": None, "repo_target": "org/beta-bank"}}),
        ("/api/deliveries/config", {"target": "org/beta-bank", "mode": "one-shot"}),
    ):
        assert client.post(path, json=body, headers=keyed(ALICE)).status_code == 403, path


@intent("INT-FC-R184")
def test_the_home_co_pilot_is_grounded_in_the_callers_floor_alone(service):
    service.config.put_setting("driver", {"base_url": "", "model": "m"}, "driver-key")
    service.fleet_chat.execute("what is next?", viewer=ALICE_CTX)
    floor = service.driver.systems[-1]
    assert "Alpha-Shop" in floor and "beta-bank" not in floor and "loose-ends" not in floor


@intent("INT-FC-R184")
def test_the_fleet_rescan_answers_the_callers_floor(client, service):
    service.refresh.execute = lambda force=False: None
    turn = client.post("/api/fleet/refresh", headers=ALICE).json()["turn"]
    for _ in range(200):
        polled = client.get(f"/api/chat/turns/{turn}", headers=ALICE).json()
        if polled["status"] != "running":
            break
    assert polled["status"] == "done"
    assert [p["repo"] for p in polled["projects"]] == ["org/Alpha-Shop"]


# INT-FC-R185: a new line belongs to its team from its first moment.

@intent("INT-FC-R185")
def test_a_members_new_repository_is_assigned_to_its_team_in_the_establish(service):
    service.establish.execute("gamma-app", "Build it", **kwargs(ALICE_CTX))
    assert service.team_roster.execute().team_of("org/gamma-app") == "alpha"


@intent("INT-FC-R185")
def test_a_member_of_several_teams_chooses_and_names_one_of_its_own(service):
    with pytest.raises(ValueError, match="choose the team"):
        service.establish.execute("delta-app", **kwargs(DAVE_CTX))
    with pytest.raises(PermissionDenied):
        service.establish.execute("delta-app", team="gamma", **kwargs(DAVE_CTX))
    service.establish.execute("delta-app", team="beta", **kwargs(DAVE_CTX))
    assert service.team_roster.execute().team_of("org/delta-app") == "beta"


@intent("INT-FC-R185")
def test_a_member_is_refused_another_teams_repository_and_an_unassigned_existing_one(service):
    with pytest.raises(PermissionDenied):
        service.establish.execute("beta-bank", **kwargs(ALICE_CTX))
    held = make_capabilities(Repos(holding={"loose-ends"}), config=service.config)
    with pytest.raises(ValueError, match="already exists"):
        held.establish.execute("loose-ends", **kwargs(ALICE_CTX))
    assert held.team_roster.execute().team_of("org/loose-ends") == ""


@intent("INT-FC-R185")
def test_a_members_claim_stays_under_the_installations_owner_and_scope(service):
    # A new repository is created under the installation's owner whatever owner the target
    # names, so naming another owner must not reach a repository another team holds.
    for target in ("ghost-owner/beta-bank", "https://github.com/ghost-owner/alpha-new"):
        with pytest.raises(PermissionDenied):
            service.establish.execute(target, **kwargs(ALICE_CTX))
    assert service.team_roster.execute().team_of("org/beta-bank") == "beta"
    narrow = replace(ALICE_CTX, claimable=frozenset({"org/foundry-*"}))
    with pytest.raises(PermissionDenied):
        service.establish.execute("outside-scope", **kwargs(narrow))
    service.establish.execute("foundry-new", **kwargs(narrow))
    assert service.team_roster.execute().team_of("org/foundry-new") == "alpha"


@intent("INT-FC-R185")
@pytest.mark.parametrize("target", [
    "https://github.com/org/loose-ends", "https://github.com/org/loose-ends.git",
    "org/loose-ends.git", "loose-ends",
])
def test_an_existing_repository_is_refused_whatever_spelling_names_it(service, target):
    class Addressed(Repos):
        """A store that reads the address exactly as written, as GitHub does."""

        def repo_exists(self, written):
            return written in {"loose-ends", "org/loose-ends"}

    held = make_capabilities(Addressed(), config=service.config)
    with pytest.raises(ValueError, match="already exists"):
        held.establish.execute(target, **kwargs(ALICE_CTX))
    assert held.team_roster.execute().team_of("org/loose-ends") == ""


@intent("INT-FC-R185")
def test_the_team_is_recorded_before_the_lines_scratch(teams_env):
    seen = []

    class Watched(Repos):
        def register(self, workspace, request="", source=(), source_name=""):
            seen.append(svc.team_roster.execute().team_of(workspace))

    svc = make_capabilities(Watched(), config=InMemoryConfigStore())
    svc.set_team.execute("alpha", "team-alpha", **kwargs(ROOT))
    svc.establish.execute("theta-app", **kwargs(ALICE_CTX))
    assert seen == ["alpha"]


@intent("INT-FC-R185")
def test_an_admin_names_any_team_or_none_and_the_door_names_none(service):
    service.establish.execute("epsilon-app", **kwargs(ROOT))
    assert service.team_roster.execute().team_of("org/epsilon-app") == ""
    service.establish.execute("zeta-app", team="beta", **kwargs(ROOT))
    assert service.team_roster.execute().team_of("org/zeta-app") == "beta"
    with pytest.raises(PermissionDenied):
        service.establish.execute("eta-app", team="beta", **kwargs(MACHINE))


# INT-FC-R186: saved agents carry an owner level.

def seed_agents(service):
    service.set_agent.execute("Install key", "claude", "", "m", "install-key", **kwargs(ROOT))
    service.set_agent.execute("Alpha seat", "claude", "", "m", "alpha-key", level="team", team="alpha", **kwargs(BOB_CTX))
    service.set_agent.execute("Beta seat", "claude", "", "m", "beta-key", level="team", team="beta", **kwargs(CAROL_CTX))
    service.set_agent.execute("Alice max", "claude", "", "m", "alice-key", level="user", **kwargs(ALICE_CTX))


@intent("INT-FC-R186")
def test_who_adds_each_level(service):
    with pytest.raises(SeatRefused):
        service.set_agent.execute("Key", "claude", "", "m", "k", **kwargs(ALICE_CTX))
    with pytest.raises(SeatRefused):
        service.set_agent.execute("Seat", "claude", "", "m", "k", level="team", team="beta", **kwargs(ALICE_CTX))
    with pytest.raises(ValueError):
        service.set_agent.execute("Seat", "claude", "", "m", "k", level="team", team="nobody", **kwargs(ROOT))
    mine = service.set_agent.execute("Mine", "claude", "", "m", "k", level="user", **kwargs(ALICE_CTX))
    assert (mine["level"], mine["owner"], mine["usable"], mine["manageable"]) == ("user", "alice@example.org", True, True)


@intent("INT-FC-R186")
def test_the_list_offers_the_install_the_teams_and_the_callers_own(service):
    seed_agents(service)

    def names(viewer):
        return sorted(a["name"] for a in service.list_agents.execute(viewer=viewer))

    assert names(ALICE_CTX) == ["Alice max", "Alpha seat", "Install key"]
    assert names(BOB_CTX) == ["Alpha seat", "Install key"]
    assert names(CAROL_CTX) == ["Beta seat", "Install key"]
    assert names(ROOT) == ["Alice max", "Alpha seat", "Beta seat", "Install key"]
    rows = {a["name"]: a for a in service.list_agents.execute(viewer=ROOT)}
    assert not rows["Alice max"]["usable"] and rows["Alice max"]["manageable"]
    assert rows["Alpha seat"]["owner"] == "alpha"
    assert all("key" not in str(row.get("credential", "")) for row in rows.values())


@intent("INT-FC-R186")
def test_another_owners_agent_is_neither_applied_overwritten_nor_deleted(service):
    seed_agents(service)
    for name in ("Alice max", "Beta seat"):
        with pytest.raises(SeatRefused):
            service.apply_agent_to_delivery.execute("org/alpha-shop", name, **kwargs(BOB_CTX))
    with pytest.raises(SeatRefused, match="already exists"):
        service.set_agent.execute("Alice max", "claude", "", "m", "theirs", level="user", **kwargs(BOB_CTX))
    with pytest.raises(SeatRefused):
        service.delete_agent.execute("Install key", **kwargs(ALICE_CTX))
    with pytest.raises(SeatRefused):
        service.delete_agent.execute("Alice max", **kwargs(BOB_CTX))
    service.apply_agent_to_delivery.execute("org/alpha-shop", "Alpha seat", **kwargs(BOB_CTX))
    service.delete_agent.execute("Alpha seat", **kwargs(ALICE_CTX))
    # An admin keeps a personal seat's owner when it edits the seat.
    service.set_agent.execute("Alice max", "claude", "", "m2", None, level="user", **kwargs(ROOT))
    assert service.config.get_setting("agent-alice-max")["owner"] == ISSUER + "#alice"


@intent("INT-FC-R186")
def test_an_agent_saved_before_levels_reads_as_an_install_agent(service):
    service.config.put_setting("agent-legacy", {"name": "Legacy", "provider": "claude", "model": "m"}, "legacy-key")
    legacy = next(a for a in service.list_agents.execute(viewer=CAROL_CTX) if a["name"] == "Legacy")
    assert (legacy["level"], legacy["usable"], legacy["manageable"]) == ("install", True, False)
    service.apply_agent_to_delivery.execute("org/beta-bank", "Legacy", **kwargs(CAROL_CTX))


@intent("INT-FC-R186")
def test_the_home_co_pilot_takes_an_install_agent_from_an_admin_alone(service):
    seed_agents(service)
    with pytest.raises(SeatRefused):
        service.apply_agent_to_driver.execute("Alpha seat", **kwargs(ROOT))
    with pytest.raises(PermissionDenied):
        service.apply_agent_to_driver.execute("Install key", **kwargs(ALICE_CTX))
    with pytest.raises(PermissionDenied):
        service.set_driver_config.execute("https://collector.example", "m", "", **kwargs(ALICE_CTX))
    assert service.apply_agent_to_driver.execute("Install key", **kwargs(ROOT)).agent == "Install key"


@intent("INT-FC-R183")
def test_every_installation_wide_setting_is_an_admins_to_write(service):
    for act in (
        lambda c: service.set_git_identity.execute("bot", "bot@example.org", "bot", None, **kwargs(c)),
        lambda c: service.set_git_roles.execute({"programmer": "bot"}, **kwargs(c)),
        lambda c: service.set_pair_credential.execute("pair", "evil.example", "me", "token", **kwargs(c)),
        lambda c: service.set_setting.execute("run-retention", {"ttl_success_days": "1"}, None, **kwargs(c)),
        lambda c: service.set_setting.execute("mcp-playbook-studio", {"user": "me"}, "pw", **kwargs(c)),
    ):
        with pytest.raises(PermissionDenied):
            act(ALICE_CTX)
    service.set_setting.execute("run-retention", {"ttl_success_days": "1"}, None, **kwargs(ROOT))


# INT-FC-R187: a personal seat's line is driven by its owner alone.

@intent("INT-FC-R187")
def test_a_personal_seats_line_is_driven_by_its_owner_alone(service):
    seed_agents(service)
    service.apply_agent_to_delivery.execute("org/alpha-shop", "Alice max", **kwargs(ALICE_CTX))
    selection = service.config.get_setting("target-alpha-shop")
    assert (selection["agent_level"], selection["agent_owner"]) == ("user", ISSUER + "#alice")

    def prepare(caller):
        return prepare_config(
            "org/alpha-shop", RunConfig("", "org/alpha-shop", True), config=service.config,
            credentials=service.apply_agent_to_delivery.credentials,
            incarnations=TestRepositoryIncarnations(), context=caller,
        )

    with pytest.raises(SeatRefused, match="alice@example.org") as refused:
        prepare(BOB_CTX)
    assert "Apply a team or install agent" in str(refused.value)
    assert prepare(ALICE_CTX)[0].repo_target == "org/alpha-shop"
    # The timeout keeps the agent, so it keeps the seat's owner.
    service.set_delivery_timeout.execute("org/alpha-shop", 7200, **kwargs(ALICE_CTX))
    with pytest.raises(SeatRefused):
        prepare(BOB_CTX)
    # A team seat drives for the team.
    service.apply_agent_to_delivery.execute("org/alpha-shop", "Alpha seat", **kwargs(BOB_CTX))
    prepare(ALICE_CTX)


@intent("INT-FC-R187")
def test_a_personal_seats_key_keeps_its_owner_wherever_it_is_pointed(service):
    seed_agents(service)
    service.apply_agent_to_delivery.execute("org/alpha-shop", "Alice max", **kwargs(ALICE_CTX))

    def prepare(caller):
        return prepare_config(
            "org/alpha-shop", RunConfig("", "org/alpha-shop", True), config=service.config,
            credentials=service.apply_agent_to_delivery.credentials,
            incarnations=TestRepositoryIncarnations(), context=caller,
        )

    # A teammate cannot point the seat's key at an endpoint of its own.
    with pytest.raises(SeatRefused):
        service.set_delivery_model.execute(
            "org/alpha-shop", "claude", "https://collector.example", "m", None, **kwargs(BOB_CTX)
        )
    # The owner repointing it keeps it theirs.
    service.set_delivery_model.execute("org/alpha-shop", "claude", "", "m2", None, **kwargs(ALICE_CTX))
    assert service.config.get_setting("target-alpha-shop")["agent"] == ""
    with pytest.raises(SeatRefused, match="a personal seat"):
        prepare(BOB_CTX)
    prepare(ALICE_CTX)
    # A teammate seating its own typed key replaces the seat, and the line is no longer hers.
    service.set_delivery_model.execute("org/alpha-shop", "claude", "", "m", "bob-key", **kwargs(BOB_CTX))
    prepare(BOB_CTX)


@intent("INT-FC-R187")
def test_a_one_shot_re_drive_on_another_persons_seat_parks_with_the_reason(service):
    from types import SimpleNamespace

    from orchestrator.application.services.maintenance.redrive_oneshot import helper_redrive_oneshot
    from maintenance_fixtures import semantic_pr

    service.config.put_setting(
        "target-alpha-shop",
        {"agent": "Alice max", "agent_level": "user", "agent_owner": ISSUER + "#alice",
         "agent_owner_label": "alice@example.org", "model": "m"},
        None,
    )
    submitted = []
    entry = {}
    scheduler = CommandContext(ISSUER + "#bob", "local", "grant", frozenset({"maintenance.drive"}),
                               frozenset({"org/alpha-shop"}), "rev", "org")
    helper_redrive_oneshot(
        "old-handle", entry, "org/alpha-shop", 7, 8, 1, findings="",
        observations=SimpleNamespace(oneshot={}), config=service.config,
        credentials=SimpleNamespace(has_delivery=lambda slug: True, delivery_ref=lambda slug: "ref"),
        studios=None, worker_image="worker:1",
        workflows=SimpleNamespace(submit=lambda workflow: submitted.append(workflow)),
        cap_delivery_config=SimpleNamespace(execute=lambda repo: {}),
        cap_git_roles=SimpleNamespace(execute=lambda: {}),
        cap_pair_credential_held=SimpleNamespace(execute=lambda key: True),
        cap_run_retention=SimpleNamespace(execute=lambda: {}),
        compiler=SimpleNamespace(compile_maintenance=lambda *a, **k: submitted.append("compiled")),
        msource=SimpleNamespace(pr=lambda repo, number: semantic_pr({"state": "open", "head": {"sha": "a" * 40}})),
        door=None, context=scheduler,
    )
    assert entry["acted"] and "alice@example.org" in entry["result"] and submitted == []


@intent("INT-FC-R187")
def test_a_personal_seats_co_pilot_answers_its_owner_alone(service):
    seed_agents(service)
    service.apply_agent_to_delivery.execute("org/alpha-shop", "Alice max", **kwargs(ALICE_CTX))
    with pytest.raises(SeatRefused):
        service.chat.execute("org/alpha-shop", "", "status?", viewer=BOB_CTX)
    assert service.chat.execute("org/alpha-shop", "", "status?", viewer=ALICE_CTX)["reply"] == "noted"


@intent("INT-FC-R187")
def test_a_direct_endpoint_or_a_line_applied_before_levels_drives_as_before():
    for selection in (
        {"agent": "", "provider": "claude", "model": "m"},
        {"agent": "Old agent", "provider": "claude", "model": "m"},
    ):
        refuse_foreign_seat(selection, BOB_CTX)
        refuse_foreign_seat(selection, MACHINE)


# INT-FC-R188: the execution door uses install agents only.

@intent("INT-FC-R188")
def test_the_execution_door_lists_applies_and_drives_install_agents_alone(service):
    seed_agents(service)
    assert [a["name"] for a in service.list_agents.execute(viewer=MACHINE)] == ["Install key"]
    with pytest.raises(SeatRefused, match="install agents only"):
        service.apply_agent_to_delivery.execute("org/bench-1", "Alpha seat", **kwargs(MACHINE))
    service.apply_agent_to_delivery.execute("org/bench-1", "Install key", **kwargs(MACHINE))
    with pytest.raises(SeatRefused, match="install agents only"):
        refuse_foreign_seat({"agent": "Alpha seat", "agent_level": "team", "agent_owner": "alpha"}, MACHINE)


# INT-FC-R189: the named-setting door is the run retention's and the MCP doors' alone.

@intent("INT-FC-R189")
def test_the_named_setting_door_writes_only_named_settings(client):
    for name in ("agent-alice-max", "target-alpha-shop", "team-alpha", "project-alpha-shop", "gitid-bot", "driver"):
        assert client.post(f"/api/config/setting/{name}", json={"fields": {"level": "install"}}, headers=keyed(ADMIN)).status_code == 403, name
        assert client.get(f"/api/config/setting/{name}", headers=ADMIN).status_code == 403, name
    assert client.post("/api/config/setting/run-retention", json={"fields": {"ttl_success_days": "3"}}, headers=keyed(ADMIN)).status_code == 200
    assert client.post("/api/config/setting/mcp-playbook-studio", json={"fields": {"user": "u"}}, headers=keyed(ADMIN)).status_code == 200
