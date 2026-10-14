from orchestrator.domain.model.platform_app import PlatformApp
from orchestrator.domain.model.repository_inventory_entry import RepositoryInventoryEntry
from delivery_fixtures import record_inputs
"""A failed scan holds the board; it never replaces it with an inferred emptiness
(INT-FC-R144).

The bug this pins: the board blanked semi-randomly and healed two minutes later. Nothing
was broken in the refresh loop - the loop worked exactly as written. `list_org_repos`
answered [] for both "the org has no repos" and "I could not ask", and `refresh()` then
assigned that over a good cache. One flaky read published "this Foundry has no projects"
as fact, over an empty state that blamed the operator's git token for it.
"""
from pytest_intent import intent
from orchestrator.adapters.inbound.http.mappers.fleet import fleet_dto
from orchestrator.adapters.outbound.memory.index import DeliveryIndex
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.services.delivery_resolution import derive_from_records
from capability_support import make_capabilities
from orchestrator.adapters.outbound.memory.studios_index import StudioStatusIndex

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FlakySource:
    """An org source that answers, then cannot be reached, then answers again - the shape
    of a transient token read or a GitHub blip, which is what actually happened."""

    def __init__(self):
        self.blip = False

    def _fail(self):
        raise SourceUnavailable('the org could not be read: <urlopen error timed out>')

    def scan(self):
        if self.blip:
            self._fail()
        return [derive_from_records('example-org/acme', True, record_inputs({'proposal.md': 'proposal accepted 2026-07-09'}))]

    def state_of(self, repo):
        return derive_from_records(repo, False, record_inputs({}))

    def list_org_repos(self):
        if self.blip:
            self._fail()
        return [RepositoryInventoryEntry(repository='example-org/acme', name='acme', updated_at='t1', topics=(), repository_id=''), RepositoryInventoryEntry(repository='example-org/shipped', name='shipped', updated_at='t2', topics=(), repository_id=''), RepositoryInventoryEntry(repository='example-org/plain', name='plain', updated_at='t3', topics=(), repository_id='')]

class FakeGateway:
    def estimatekit_slugs(self):
        return []

    def protopane_slugs(self):
        return []

    def playbook_repo(self):
        return ""


    def health(self):
        return []

    def artifacts_for(self, slug):
        return {}

    def platform_apps(self):
        return [PlatformApp(name='shipped', repository='shipped', onboarded=True, status='running', hostname='', revision='', role='output')]

def _service(source):
    return make_capabilities(FakeRepos(), index=DeliveryIndex(), source=source, studios=FakeGateway(), studio_index=StudioStatusIndex())

@intent('INT-FC-R144')
def test_a_failed_scan_holds_the_board_instead_of_emptying_it():
    src = FlakySource()
    svc = _service(src)
    svc.refresh.execute()
    assert [p.name for p in svc.fleet.execute()] == ['acme', 'shipped', 'plain']
    src.blip = True
    svc.refresh.execute()
    assert [p.name for p in svc.fleet.execute()] == ['acme', 'shipped', 'plain']
    src.blip = False
    svc.refresh.execute()
    assert [p.name for p in svc.fleet.execute()] == ['acme', 'shipped', 'plain']

@intent('INT-FC-R144')
def test_a_failed_scan_leaves_the_delivery_index_standing():
    src = FlakySource()
    svc = _service(src)
    svc.refresh.execute()
    assert [d.repo for d in svc.list_deliveries.execute()] == ['example-org/acme']
    src.blip = True
    svc.refresh.execute()
    assert [d.repo for d in svc.list_deliveries.execute()] == ['example-org/acme']

@intent('INT-FC-R144')
def test_a_held_board_says_it_is_held_and_stamps_when_not_each_failed_tick():
    src = FlakySource()
    svc = _service(src)
    svc.refresh.execute()
    assert svc.fleet_staleness.execute() == (None, '')
    src.blip = True
    svc.refresh.execute()
    since, why = svc.fleet_staleness.execute()
    assert since is not None and 'could not be read' in why
    svc.refresh.execute()
    assert svc.fleet_staleness.execute()[0] == since
    src.blip = False
    svc.refresh.execute()
    assert svc.fleet_staleness.execute() == (None, '')

@intent('INT-FC-R144')
def test_the_fleet_read_carries_its_own_staleness():
    src = FlakySource()
    svc = _service(src)
    svc.refresh.execute()
    fresh = fleet_dto(svc.fleet.execute(), *svc.fleet_staleness.execute())
    assert fresh['stale_since'] is None and fresh['stale_reason'] == ''
    src.blip = True
    svc.refresh.execute()
    held = fleet_dto(svc.fleet.execute(), *svc.fleet_staleness.execute())
    assert held['stale_since'] is not None
    assert len(held['projects']) == 3

@intent('INT-FC-R144')
def test_an_org_that_genuinely_has_no_repos_is_still_empty():

    class EmptyOrg:

        def scan(self):
            return []

        def state_of(self, repo):
            return derive_from_records(repo, False, record_inputs({}))

        def list_org_repos(self):
            return []
    svc = _service(EmptyOrg())
    svc.refresh.execute()
    assert svc.fleet.execute() == []
    assert svc.fleet_staleness.execute() == (None, '')


@intent("INT-FC-R144")
def test_malformed_github_inventory_retains_the_previous_board():
    from orchestrator.adapters.outbound.github.github_delivery_source import GitHubDeliverySource

    class InventorySource(GitHubDeliverySource):
        payload = [{"full_name": "example-org/plain", "name": "plain", "id": 12}]

        def scan(self):
            return []

        def _get(self, path, token):
            assert path.startswith("/orgs/example-org/repos")
            return self.payload

    source = InventorySource("example-org", lambda: "credential")
    service = _service(source)
    service.refresh.execute()
    assert [item.repo for item in service.fleet.execute()] == ["example-org/plain"]
    source.payload = {"message": "invalid inventory"}
    service.refresh.execute()
    assert [item.repo for item in service.fleet.execute()] == ["example-org/plain"]
    assert "malformed" in service.fleet_staleness.execute()[1]
    source.payload = []
    service.refresh.execute()
    assert service.fleet.execute() == []
    assert service.fleet_staleness.execute() == (None, "")


class ScanFails(FlakySource):
    """The delivery scan fails while the fleet read beside it still answers."""

    def scan(self):
        if self.blip:
            raise SourceUnavailable("delivery observation could not be read")
        return super().scan()

    def list_org_repos(self):
        blip, self.blip = self.blip, False
        try:
            return super().list_org_repos()
        finally:
            self.blip = blip

    def read_config(self, repo, *, revision=""):
        return {}


DELIVERY_READS = (
    "/api/deliveries",
    "/api/deliveries/state?repo=example-org/acme",
    "/api/deliveries/overview?repo=example-org/acme",
)


def _delivery_freshness(svc):
    from fastapi.testclient import TestClient
    from orchestrator.adapters.inbound.http.app import create_app

    client = TestClient(create_app(svc))
    return [client.get(read).json()["freshness"] for read in DELIVERY_READS]


@intent("INT-FC-R144")
def test_a_failed_delivery_scan_marks_the_delivery_reads_held_while_the_fleet_reads():
    """The fleet read succeeding on the same tick must not clear the delivery hold: the
    index is what the delivery reads serve, and it was not refreshed."""
    import datetime
    import time

    src = ScanFails()
    svc = _service(src)
    svc.refresh.execute(force=True)
    assert [f["state"] for f in _delivery_freshness(svc)] == ["fresh"] * 3
    last_good = datetime.datetime.now(datetime.UTC)
    time.sleep(1.1)  # the failed tick lands in a later second than the last good scan
    src.blip = True
    svc.refresh.execute(force=True)
    assert svc.fleet_staleness.execute() == (None, "")
    held = _delivery_freshness(svc)
    for read, freshness in zip(DELIVERY_READS, held):
        assert freshness["state"] == "stale", read
        assert freshness["reason_code"] == "source_unavailable", read
        assert freshness["coverage"]["complete"] is False, read
        assert datetime.datetime.fromisoformat(freshness["observed_at"]) <= last_good, read
    svc.refresh.execute(force=True)
    assert [f["observed_at"] for f in _delivery_freshness(svc)] == [
        f["observed_at"] for f in held
    ]
    src.blip = False
    svc.refresh.execute(force=True)
    assert [f["state"] for f in _delivery_freshness(svc)] == ["fresh"] * 3


@intent("INT-FC-R144")
def test_a_delivery_scan_that_never_completed_reads_unavailable():
    src = ScanFails()
    src.blip = True
    svc = _service(src)
    svc.refresh.execute(force=True)
    for read, freshness in zip(DELIVERY_READS, _delivery_freshness(svc)):
        assert freshness["state"] == "unavailable", read
        assert freshness["observed_at"] is None, read
