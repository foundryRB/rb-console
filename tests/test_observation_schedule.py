"""Due collection holds a healthy fleet inside the freshness window at the real cadence.

The collector runs against a controlled clock the way the scheduler drives it: the tick's
other observations (`overhead`), then the metadata collection, whose source reads take
simulated time (`cost` per read, the effective cost once reads run in parallel), then the
observation interval. A live install measured about 2.2 seconds of reads per repository
four at a time, beside some 36 seconds of the tick's other observations.
"""
from __future__ import annotations

import threading
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pytest_intent import intent

from orchestrator.application.services.projections.observation_schedule import (
    COLLECTION_DUE,
    FRESHNESS_WINDOW,
    OBSERVATION_INTERVAL,
)
from orchestrator.application.use_cases.projections.refresh_metadata import (
    RefreshMetadata,
)
from orchestrator.application.use_cases.projections.snapshot_metadata import (
    SnapshotMetadata,
)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 6, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Published(dict):
    """Observation metadata that checks each repository's outgoing observation at the
    instant it is replaced, the oldest that observation ever gets."""

    def __init__(self, fleet: Fleet) -> None:
        super().__init__()
        self.fleet = fleet

    def __setitem__(self, repo, value) -> None:
        if self.fleet.warm and repo and self.fleet.state(repo) != "fresh":
            self.fleet.expired_before_collection.append(repo)
        super().__setitem__(repo, value)


class Fleet:
    """A fleet whose source reads each cost `cost` seconds; failing repositories raise."""

    def __init__(self, size: int, cost: float, overhead: float = 30, failing: tuple[str, ...] = ()) -> None:
        self.clock = Clock()
        self.cost = cost
        self.overhead = overhead
        self.failing = set(failing)
        self.repos = [f"org/app{i:03}" for i in range(size)]
        self.observations = SimpleNamespace(
            metadata=Published(self), fleet=[SimpleNamespace(repo=repo) for repo in self.repos]
        )
        self.snapshot = SnapshotMetadata(self.observations, clock=self.clock)
        self.collections: list[tuple[str, datetime]] = []
        self.starts: list[datetime] = []
        self.warm = False
        self.expired_before_collection: list[str] = []
        self.collector = RefreshMetadata(
            observations=self.observations,
            maintenance=SimpleNamespace(execute=self.first_read),
            promotion=SimpleNamespace(execute=self.read),
            options=SimpleNamespace(execute=self.read),
            config=SimpleNamespace(execute=self.read),
            workers=1,
            clock=self.clock,
        )

    def first_read(self, repo: str) -> dict:
        self.collections.append((repo, self.clock()))
        return self.read(repo)

    def read(self, repo: str) -> dict:
        self.clock.advance(self.cost)
        if repo in self.failing:
            raise RuntimeError("source unavailable")
        return {"repo": repo}

    def state(self, repo: str) -> str:
        return self.snapshot.execute(repo)["freshness"]["state"]

    def tick(self) -> dict:
        self.clock.advance(self.overhead)
        self.starts.append(self.clock())
        report = self.collector.execute()
        self.clock.advance(OBSERVATION_INTERVAL.total_seconds())
        return report


@intent("INT-FC-R169")
@pytest.mark.parametrize(
    ("size", "cost", "overhead"),
    [(60, 0.25, 30), (75, 0.25, 30), (60, 0.7, 30), (75, 0.7, 30), (75, 0.55, 36), (60, 0.25, 90)],
)
def test_a_healthy_fleet_stays_fully_fresh_at_the_scheduler_cadence(size, cost, overhead):
    """Each repository read costs four source calls, 1 to 2.8 seconds per repository, beside
    30 to 90 seconds of the tick's other observations. After the cold start, every tick
    reports complete coverage and no repository is ever read through an HTTP query as
    anything but fresh, sampled before each tick, after each tick, and at the instant its
    observation is replaced."""
    fleet = Fleet(size, cost, overhead)
    warmup = -(-size // fleet.collector.batch_size)
    for _ in range(warmup):
        fleet.tick()
    fleet.warm = True
    for _ in range(40):
        assert all(fleet.state(repo) == "fresh" for repo in fleet.repos)
        report = fleet.tick()
        assert report["complete"] is True
        assert report["observed"] == report["fresh"] == report["total"] == size
        assert all(fleet.state(repo) == "fresh" for repo in fleet.repos)
    assert fleet.expired_before_collection == []


@intent("INT-FC-R169")
@pytest.mark.parametrize("size", [60, 75])
def test_collection_stays_within_one_batch_and_one_read_per_due_period(size):
    """Freshness is bought with the request rate it needs and no more: no tick reads more
    than its batch, and no repository is read again before it is due."""
    fleet = Fleet(size, 0.55, 36)
    for _ in range(40):
        before = len(fleet.collections)
        fleet.tick()
        assert len(fleet.collections) - before <= fleet.collector.batch_size
    last: dict[str, datetime] = {}
    for repo, at in fleet.collections:
        if repo in last:
            assert at - last[repo] >= COLLECTION_DUE
        last[repo] = at
    elapsed = fleet.collections[-1][1] - fleet.collections[0][1]
    assert len(fleet.collections) <= size * (elapsed / COLLECTION_DUE + 1)


@intent("INT-FC-R169")
def test_failed_and_expired_observations_stay_truthfully_stale():
    fleet = Fleet(75, 0.25, failing=("org/app007",))
    for _ in range(4):
        report = fleet.tick()
    assert fleet.state("org/app007") == "unavailable"
    assert report["complete"] is False
    attempts = sum(repo == "org/app007" for repo, _ in fleet.collections)
    for _ in range(20):
        assert fleet.tick()["complete"] is False
    retried = sum(repo == "org/app007" for repo, _ in fleet.collections) - attempts
    elapsed = fleet.starts[-1] - fleet.starts[-21]
    assert 1 <= retried <= elapsed / COLLECTION_DUE + 1
    fleet.failing.clear()
    fleet.collector.execute(sweep=True)
    assert fleet.state("org/app007") == "fresh"
    fleet.observations.metadata["org/app003"]["freshness"]["observed_at"] = (
        fleet.clock() - FRESHNESS_WINDOW - timedelta(seconds=1)
    ).isoformat()
    snapshot = fleet.snapshot.execute("org/app003")["freshness"]
    assert (snapshot["state"], snapshot["reason_code"]) == ("stale", "observation_expired")
    assert fleet.collector.execute()["complete"] is False


@intent("INT-FC-R169")
def test_a_batch_is_collected_in_parallel_within_the_caller_context():
    """Repositories in one batch are read a few at a time, and each read carries the
    caller's context, which marks scheduled reads as background traffic."""
    marker: ContextVar[str] = ContextVar("marker", default="")
    workers = 4
    barrier = threading.Barrier(workers, timeout=5)
    seen: list[str] = []

    def read(repo: str) -> dict:
        seen.append(marker.get())
        return {"repo": repo}

    def first_read(repo: str) -> dict:
        barrier.wait()
        return read(repo)

    observations = SimpleNamespace(metadata={}, fleet=[SimpleNamespace(repo=f"org/app{i}") for i in range(workers)])
    collector = RefreshMetadata(
        observations=observations,
        maintenance=SimpleNamespace(execute=first_read),
        promotion=SimpleNamespace(execute=read),
        options=SimpleNamespace(execute=read),
        config=SimpleNamespace(execute=read),
        workers=workers,
    )
    marker.set("background")
    report = collector.execute()
    assert report["complete"] is True
    assert seen == ["background"] * (4 * workers)


@intent("INT-FC-R107")
def test_an_explicit_sweep_reads_every_repository_regardless_of_due_time():
    fleet = Fleet(75, 0.25)
    fleet.tick()
    before = len(fleet.collections)
    report = fleet.collector.execute(sweep=True)
    assert len(fleet.collections) - before == 75
    assert report["complete"] is True
