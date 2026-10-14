from execution_fixtures import execution_graph, run_rows
from delivery_fixtures import record_inputs
"""The Runs surface reads live Argo Workflows: list them (newest first) and read one run's
node DAG. The kubectl parse is pure, and the service delegates to the executor. Audit: csd-intent ."""
from capability_support import invoke_helper
from capability_support import command_kwargs
import json
from pytest_intent import intent
from orchestrator.adapters.outbound.argo.argo_workflow_runner import parse_graph, parse_runs, resume_patch
from capability_support import make_capabilities
WF_LIST = {'items': [{'metadata': {'name': 'delivery-acme-abc', 'creationTimestamp': '2026-07-09T10:00:00Z', 'labels': {'foundry-console/run': 'r-1', 'foundry-console/mode': 'one-shot'}}, 'status': {'phase': 'Running', 'startedAt': '2026-07-09T10:00:01Z', 'progress': '1/4'}}, {'metadata': {'name': 'delivery-beta-xyz', 'creationTimestamp': '2026-07-09T11:00:00Z', 'labels': {'foundry-console/run': 'r-2'}}, 'status': {'phase': 'Succeeded'}}]}
WF_ONE = {'metadata': {'name': 'delivery-acme-abc'}, 'status': {'phase': 'Running', 'nodes': {'n1': {'id': 'n1', 'displayName': 'worker-scope', 'type': 'Pod', 'phase': 'Succeeded', 'templateName': 'worker-scope'}, 'n2': {'id': 'n2', 'displayName': 'gate-proposal', 'type': 'Suspend', 'phase': 'Running'}}}}

class FakeRunner:

    def metadata_of(self, handle):
        from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
        return WorkflowMetadata("org/app", "v1", handle, "maintenance", "")

    def submit(self, wf):
        return 'x'

    def status(self, handle):
        return 'Running'

    def list_runs(self):
        return parse_runs(WF_LIST)

    def graph(self, handle):
        return execution_graph(parse_graph(WF_ONE))

class FakeRepos:

    def list_delivery_repos(self):
        return []

@intent('INT-FC-R42')
def test_runs_and_graph_parse_argo_and_delegate():
    runs = parse_runs(WF_LIST)
    assert [r.name for r in runs] == ['delivery-beta-xyz', 'delivery-acme-abc']
    acme = next((r for r in runs if r.name == 'delivery-acme-abc'))
    assert acme.handle == 'live:workflow.argoproj.io/delivery-acme-abc'
    assert acme.mode == 'one-shot' and acme.phase == 'Running'
    graph = parse_graph(WF_ONE)
    assert graph.phase == 'Suspended'
    kinds = {n.name: n.kind for n in graph.nodes}
    assert kinds['worker-scope'] == 'worker' and kinds['gate-proposal'] == 'gate'
    svc = make_capabilities(FakeRepos(), workflows=FakeRunner())
    svc.refresh.execute()
    assert len(svc.runs.execute()) == 2
    assert svc.run_graph.execute('live:workflow.argoproj.io/delivery-acme-abc').phase == 'Suspended'
WF_SUSPENDED = {'status': {'nodes': {'n1': {'id': 'n1', 'type': 'Pod', 'phase': 'Succeeded'}, 'n2': {'id': 'n2', 'type': 'Suspend', 'phase': 'Running'}, 'n3': {'id': 'n3', 'type': 'Suspend', 'phase': 'Succeeded'}}}}

@intent('INT-FC-R43')
def test_resume_patch_targets_only_live_suspends_and_controls_delegate():
    ops = resume_patch(WF_SUSPENDED)
    assert ops == [{'op': 'replace', 'path': '/status/nodes/n2/phase', 'value': 'Succeeded'}]

    class CtrlRunner(FakeRunner):

        def stop(self, handle, terminate=False, reason='operator', *, expected_version=None):
            assert reason == 'operator'
            return 'Terminate' if terminate else 'Stop'

        def resume(self, handle, *, expected_version=None):
            return 'resumed:1'

        def logs(self, handle, tail=400):
            return 'pod/x hello'
    svc = make_capabilities(FakeRepos(), workflows=CtrlRunner())
    assert svc.stop_run.execute('live:x', terminate=True, **command_kwargs('org/app'))['shutdown'] == 'Terminate'
    assert svc.resume_run.execute('live:x', **command_kwargs('org/app'))['resumed'] == 'resumed:1'
    assert svc.run_logs.execute('live:x') == 'pod/x hello'

def test_run_logs_hold_a_stable_container_order(monkeypatch):
    """logs() reads one container at a time: pods in creation order, init and wait before
    main within each pod, identical output on every poll - the terminated containers'
    lines never shuffle in front of the live main tail."""
    import json as _json
    import orchestrator.adapters.outbound.argo.argo_workflow_runner as wr
    pods_json = {'items': [{'metadata': {'name': 'pod-a'}, 'spec': {'initContainers': [{'name': 'init'}], 'containers': [{'name': 'main'}, {'name': 'wait'}]}}, {'metadata': {'name': 'pod-b'}, 'spec': {'initContainers': [{'name': 'init'}], 'containers': [{'name': 'wait'}, {'name': 'main'}]}}]}

    class Proc:

        def __init__(self, out: str) -> None:
            self.returncode, self.stdout, self.stderr = (0, out, '')

    def fake_run(args, **kwargs):
        if args[:3] == ['kubectl', 'get', 'pods']:
            return Proc(_json.dumps(pods_json))
        pod, container = (args[2], args[6])
        return Proc(f'{container}-line-of-{pod}\n')
    monkeypatch.setattr(wr.subprocess, 'run', fake_run)
    runner = wr.ArgoWorkflowRunner(namespace='x')
    out = runner.logs('live:workflow.argoproj.io/w1')
    assert out.splitlines() == ['[pod/pod-a/init] init-line-of-pod-a', '[pod/pod-a/wait] wait-line-of-pod-a', '[pod/pod-a/main] main-line-of-pod-a', '[pod/pod-b/init] init-line-of-pod-b', '[pod/pod-b/wait] wait-line-of-pod-b', '[pod/pod-b/main] main-line-of-pod-b']
    assert runner.logs('live:workflow.argoproj.io/w1') == out

def test_parked_gates_read_suspended_not_running():
    """A workflow parked on a gate suspend reads Suspended in the run row and the graph
    node, so a wait for a signature never shows as work in flight."""
    wf = {'metadata': {'name': 'delivery-acme-abc', 'labels': {}, 'creationTimestamp': 't'}, 'status': {'phase': 'Running', 'nodes': {'n1': {'id': 'n1', 'displayName': 'scope(0)', 'type': 'Pod', 'phase': 'Succeeded'}, 'n2': {'id': 'n2', 'displayName': 'gate-proposal', 'type': 'Suspend', 'phase': 'Running'}}}}
    rows = parse_runs({'items': [wf]})
    assert rows[0].phase == 'Suspended'
    graph = parse_graph(wf)
    assert graph.phase == 'Suspended'
    by_name = {n.name: n.phase for n in graph.nodes}
    assert by_name['gate-proposal'] == 'Suspended'
    assert by_name['scope(0)'] == 'Succeeded'

def test_running_worker_is_not_promoted_to_suspended():
    """The promotion fires only on a PARKED gate. A workflow whose live node is a worker Pod
    (no suspend waiting) stays Running in both the run row and the graph, so real work in
    flight never reads as a wait for a signature."""
    wf = {'metadata': {'name': 'delivery-acme-abc', 'labels': {}, 'creationTimestamp': 't'}, 'status': {'phase': 'Running', 'nodes': {'n1': {'id': 'n1', 'displayName': 'gate-proposal', 'type': 'Suspend', 'phase': 'Succeeded'}, 'n2': {'id': 'n2', 'displayName': 'worker-design(0)', 'type': 'Pod', 'phase': 'Running'}}}}
    assert parse_runs({'items': [wf]})[0].phase == 'Running'
    assert parse_graph(wf).phase == 'Running'

def _wf(name: str, phase: str, stop: str | None=None, nodes: dict | None=None) -> dict:
    labels = {'foundry-console/run': 'r-1'}
    if stop:
        labels['foundry-console/stop'] = stop
    return {'metadata': {'name': name, 'labels': labels, 'creationTimestamp': 't'}, 'status': {'phase': phase, **({'nodes': nodes} if nodes else {})}}

@intent('INT-FC-R124')
def test_a_stopped_run_is_named_a_stop_not_a_failure():
    """A run the Console stopped reads Stopped, not the Failed a shutdown produces, and
    carries WHO stopped it. The band showed a wall of red 'Failed' rows for a line iterated
    on across a week - every one of them a run the Console had closed on the operator's next
    drive - with no way to tell them from a run that genuinely died."""
    rows = {r.name: r for r in parse_runs({'items': [_wf('delivery-acme-a', 'Failed', stop='superseded'), _wf('delivery-acme-b', 'Failed', stop='operator'), _wf('delivery-acme-c', 'Failed'), _wf('delivery-acme-d', 'Succeeded', stop='superseded'), _wf('delivery-acme-e', 'Running', stop='superseded')]})}
    assert rows['delivery-acme-a'].phase == 'Stopped'
    assert rows['delivery-acme-a'].stop_reason == 'superseded'
    assert rows['delivery-acme-b'].phase == 'Stopped'
    assert rows['delivery-acme-b'].stop_reason == 'operator'
    assert rows['delivery-acme-c'].phase == 'Failed'
    assert rows['delivery-acme-c'].stop_reason is None
    assert rows['delivery-acme-d'].phase == 'Succeeded'
    assert rows['delivery-acme-e'].phase == 'Stopping'

@intent('INT-FC-R124')
def test_the_stop_derivation_is_one_derivation_shared_by_row_and_graph():
    """The row and the node graph run through the SAME derivation, so the band, the cockpit
    pill and the maintenance pane can never disagree about what a run is doing - the rule the
    gate promotion already holds."""
    parked = _wf('delivery-acme-p', 'Running', stop='superseded', nodes={'n1': {'id': 'n1', 'displayName': 'gate-proposal', 'type': 'Suspend', 'phase': 'Running'}})
    assert parse_runs({'items': [parked]})[0].phase == 'Stopping'
    assert parse_graph(parked).phase == 'Stopping'
    assert parse_graph(parked).stop_reason == 'superseded'
    done = _wf('delivery-acme-q', 'Failed', stop='operator')
    assert parse_runs({'items': [done]})[0].phase == 'Stopped'
    assert parse_graph(done).phase == 'Stopped'

@intent('INT-FC-R124')
def test_the_stop_mark_and_the_shutdown_land_in_one_patch(monkeypatch):
    """The mark is written by the same act that requests the shutdown. Two calls would leave
    a window in which the run is a bare unattributed failure - and one that opens only when
    the second call fails is the window nobody would ever see in testing."""
    from orchestrator.adapters.outbound.argo.argo_workflow_runner import ArgoWorkflowRunner
    seen: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = ''
        stderr = ''

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        result = Done()
        if cmd[:2] == ["kubectl", "get"]:
            result.stdout = json.dumps({"metadata": {"resourceVersion": "v1"}})
        return result
    monkeypatch.setattr('orchestrator.adapters.outbound.argo.argo_workflow_runner.subprocess.run', fake_run)
    runner = ArgoWorkflowRunner(namespace='fc')
    runner.stop('live:workflow.argoproj.io/delivery-acme-a', reason='superseded')
    patches = [cmd for cmd in seen if '-p' in cmd]
    patch = json.loads(patches[0][patches[0].index('-p') + 1])
    assert patch['spec']['shutdown'] == 'Stop'
    assert patch['metadata']['labels']['foundry-console/stop'] == 'superseded'
    runner.stop('live:workflow.argoproj.io/delivery-acme-b', terminate=True)
    patches = [cmd for cmd in seen if '-p' in cmd]
    patch = json.loads(patches[1][patches[1].index('-p') + 1])
    assert patch['spec']['shutdown'] == 'Terminate'
    assert patch['metadata']['labels']['foundry-console/stop'] == 'operator'

class DictLogStore:
    def save_metadata(self, name, metadata):
        self.metadata[name] = metadata

    def all_metadata(self):
        return list(self.metadata.values())

    """The RunLogStore port over a dict, for the snapshot tests."""

    def __init__(self):
        self.saved = {}
        self.metadata = {}
        self.prune_horizons = []

    def save(self, name, text, prune_after_seconds=None):
        self.saved[name] = text
        self.prune_horizons.append(prune_after_seconds)

    def load(self, name):
        return self.saved.get(name)

    def has(self, name):
        return name in self.saved

@intent('INT-FC-R108')
def test_terminal_run_logs_survive_pod_gc_via_snapshot():
    """Reading the runs list snapshots each terminal run's logs once; a log read whose
    live pods are gone serves the snapshot. An empty capture still marks the run swept."""

    class Runner(FakeRunner):

        def __init__(self):
            self.log_reads = []
            self.live = '[pod/p-beta-1/main] built\n[pod/p-beta-1/main] shipped'

        def list_runs(self):
            return parse_runs(WF_LIST)

        def logs(self, handle, tail=400):
            self.log_reads.append(handle)
            return self.live
    runner, store = (Runner(), DictLogStore())
    svc = make_capabilities(FakeRepos(), workflows=runner, run_log_store=store)
    svc.refresh.execute()
    assert list(store.saved) == ['delivery-beta-xyz']
    assert store.saved['delivery-beta-xyz'] == runner.live
    svc.refresh.execute()
    assert len(runner.log_reads) == 1
    runner.live = ''
    assert svc.run_logs.execute('live:workflow.argoproj.io/delivery-beta-xyz').endswith('shipped')
    assert svc.run_logs.execute('live:workflow.argoproj.io/delivery-ghost-zzz') == ''

@intent('INT-FC-R108')
def test_a_superseded_runs_logs_are_captured_like_any_other_terminal_run():
    """A stopped run is terminal and its pods are GC'd on the same clock, so it is swept
    too - and it is the row most likely to be reached for later ("what did the previous
    attempt do differently?"). Naming the stop must not quietly re-open the pain decision
    0002 closed: a re-drive destroying the previous run's evidence. A run still DRAINING is
    not swept - it is still writing the logs the snapshot would capture."""

    class Runner(FakeRunner):

        def list_runs(self):
            return parse_runs({'items': [_wf('delivery-acme-gone', 'Failed', stop='superseded'), _wf('delivery-acme-going', 'Running', stop='superseded')]})

        def logs(self, handle, tail=400):
            return '[pod/p/main] the previous attempt'
    store = DictLogStore()
    svc = make_capabilities(FakeRepos(), workflows=Runner(), run_log_store=store)
    svc.refresh.execute()
    assert list(store.saved) == ['delivery-acme-gone']

@intent('INT-FC-R108')
def test_the_background_tick_captures_without_a_cockpit_open():
    """The capture rides the refresh tick, not a page read: a run that finishes while
    nobody is looking is still snapshotted, inside the pod-GC delay. The judging chore
    reuses the rows the tick already read rather than reading the executor again."""

    class Runner(FakeRunner):

        def __init__(self):
            self.list_calls = 0

        def list_runs(self):
            self.list_calls += 1
            return parse_runs(WF_LIST)

        def logs(self, handle, tail=400):
            return '[pod/p/main] overnight output'
    runner, store = (Runner(), DictLogStore())
    svc = make_capabilities(FakeRepos(), workflows=runner, run_log_store=store)
    svc.refresh.execute()
    assert store.saved['delivery-beta-xyz'] == '[pod/p/main] overnight output'
    before = runner.list_calls
    invoke_helper(svc, '_judge_oneshot_runs', parse_runs(WF_LIST))
    assert runner.list_calls == before

@intent('INT-FC-R108')
def test_empty_capture_marks_a_lost_run_swept():
    """A terminal run whose pods were reclaimed before any sweep is probed exactly once:
    the empty capture is saved as the swept marker, not retried on every poll."""

    class Runner(FakeRunner):

        def __init__(self):
            self.log_reads = 0

        def logs(self, handle, tail=400):
            self.log_reads += 1
            return ''
    runner, store = (Runner(), DictLogStore())
    svc = make_capabilities(FakeRepos(), workflows=runner, run_log_store=store)
    svc.refresh.execute()
    svc.refresh.execute()
    assert runner.log_reads == 1
    assert store.saved['delivery-beta-xyz'] == ''

@intent('INT-FC-R109')
def test_node_scoped_logs_from_live_pods_and_from_snapshot():
    """A node-scoped read returns only that node's pod lines - the live executor read
    passes the node down; the snapshot fallback filters the stored lines by the same
    pod-matching rule (the node id itself, or a pod name ending in its trailing token)."""
    from orchestrator.domain.services.run_history import filter_node_lines, pod_matches_node
    node = 'delivery-acme-abc-3216428971'
    assert pod_matches_node('delivery-acme-abc-3216428971', node)
    assert pod_matches_node('delivery-acme-abc-worker-scope-3216428971', node)
    assert not pod_matches_node('delivery-acme-abc-worker-scope-99', node)
    text = '[pod/delivery-acme-abc-worker-scope-3216428971/main] scoped\n[pod/delivery-acme-abc-worker-build-777/main] built\nno prefix line'
    assert filter_node_lines(text, node) == '[pod/delivery-acme-abc-worker-scope-3216428971/main] scoped'

    class Runner(FakeRunner):

        def __init__(self):
            self.node_reads = []

        def logs(self, handle, tail=400, node_id=None):
            self.node_reads.append(node_id)
            return '[pod/x-1/main] live line' if node_id else ''
    runner = Runner()
    svc = make_capabilities(FakeRepos(), workflows=runner)
    assert svc.run_logs.execute('live:workflow.argoproj.io/w', node_id='n-1') == '[pod/x-1/main] live line'
    assert runner.node_reads == ['n-1']

    class DarkRunner(FakeRunner):

        def logs(self, handle, tail=400, node_id=None):
            return ''
    store = DictLogStore()
    store.saved['w'] = text
    svc = make_capabilities(FakeRepos(), workflows=DarkRunner(), run_log_store=store)
    assert svc.run_logs.execute('live:workflow.argoproj.io/w', node_id=node).endswith('scoped')
    assert svc.run_logs.execute('live:workflow.argoproj.io/w') == text

def test_adapter_scopes_live_log_read_to_the_nodes_pod(monkeypatch):
    """The kubectl-backed logs() reads only the matching node's pod when scoped."""
    import json as _json
    import orchestrator.adapters.outbound.argo.argo_workflow_runner as wr
    pods_json = {'items': [{'metadata': {'name': 'w1-worker-scope-111'}, 'spec': {'containers': [{'name': 'main'}]}}, {'metadata': {'name': 'w1-worker-build-222'}, 'spec': {'containers': [{'name': 'main'}]}}]}

    class Proc:

        def __init__(self, out: str) -> None:
            self.returncode, self.stdout, self.stderr = (0, out, '')

    def fake_run(args, **kwargs):
        if args[:3] == ['kubectl', 'get', 'pods']:
            return Proc(_json.dumps(pods_json))
        return Proc(f'line-of-{args[2]}\n')
    monkeypatch.setattr(wr.subprocess, 'run', fake_run)
    runner = wr.ArgoWorkflowRunner(namespace='x')
    out = runner.logs('live:workflow.argoproj.io/w1', node_id='w1-111')
    assert out == '[pod/w1-worker-scope-111/main] line-of-w1-worker-scope-111'

@intent('INT-FC-R110')
def test_run_retention_is_an_operator_setting_with_clamped_defaults():
    """The GC horizons are the Settings page's run-retention setting, read live per
    compile: defaults hold when nothing is stored, stored values ride into the compiled
    GC block, garbage clamps back to defaults, and the failure TTL never falls below the
    success TTL. The snapshot prune horizon is the failure TTL, so a run's row and its
    log file expire together."""

    class Config:

        def __init__(self, fields):
            self.fields = fields

        def get_setting(self, name):
            return {**self.fields, 'configured': False}

    def svc_with(fields):
        return make_capabilities(FakeRepos(), workflows=FakeRunner(), config=Config(fields))
    assert svc_with({}).run_retention.execute() == {'pod_gc_delay_hours': 1, 'ttl_success_days': 7, 'ttl_failure_days': 30}
    svc = svc_with({'pod_gc_delay_hours': '2', 'ttl_success_days': '3', 'ttl_failure_days': '14'})
    from orchestrator.adapters.outbound.argo.retention import gc_policy
    block = gc_policy(**svc.run_retention.execute())
    assert block['podGC']['deleteDelayDuration'] == '2h'
    assert block['ttlStrategy']['secondsAfterSuccess'] == 3 * 86400
    assert block['ttlStrategy']['secondsAfterFailure'] == 14 * 86400
    ret = svc_with({'pod_gc_delay_hours': 'nope', 'ttl_success_days': '10', 'ttl_failure_days': '2'}).run_retention.execute()
    assert ret == {'pod_gc_delay_hours': 1, 'ttl_success_days': 10, 'ttl_failure_days': 10}

    class Runner(FakeRunner):

        def logs(self, handle, tail=400):
            return '[pod/p/main] out'
    store = DictLogStore()
    svc = make_capabilities(FakeRepos(), workflows=Runner(), config=Config({'ttl_failure_days': '14'}), run_log_store=store)
    svc.refresh.execute()
    assert store.prune_horizons == [14 * 86400]

def test_file_run_log_store_round_trips_and_sanitizes(tmp_path):
    from orchestrator.adapters.outbound.archives.file_run_log_store import FileRunLogStore
    store = FileRunLogStore(root=str(tmp_path / 'run-logs'))
    assert store.load('delivery-x-1') is None and (not store.has('delivery-x-1'))
    store.save('delivery-x-1', 'hello')
    assert store.has('delivery-x-1') and store.load('delivery-x-1') == 'hello'
    store.save('../evil/name', 'contained')
    assert store.load('../evil/name') == 'contained'
    assert all((p.parent == tmp_path / 'run-logs' for p in (tmp_path / 'run-logs').iterdir()))

@intent('INT-FC-R110')
def test_the_prune_reclaims_a_runs_record_with_its_log_file(tmp_path):
    """Past the horizon a run's log file goes with its record, and a record with no log
    file ages out on its own last write; anything written inside the horizon stays."""
    import os
    import time
    from orchestrator.adapters.outbound.archives.file_run_log_store import FileRunLogStore
    old = time.time() - 40 * 86400
    files = {'expired.log': old, 'expired.log.json': time.time(), 'orphan.log.json': old,
             'kept.log': time.time(), 'kept.log.json': time.time(), 'listed.log.json': time.time()}
    for name, mtime in files.items():
        (tmp_path / name).write_text('{}', encoding='utf-8')
        os.utime(tmp_path / name, (mtime, mtime))
    FileRunLogStore(root=str(tmp_path)).save('new', 'tail', prune_after_seconds=30 * 86400)
    assert sorted((p.name for p in tmp_path.iterdir())) == ['kept.log', 'kept.log.json', 'listed.log.json', 'new.log']

class _LazyEntry:
    """A directory entry whose stat reads the file at call time, as it does on Linux."""

    def __init__(self, path):
        self.path = str(path)
        self.name = path.name

    def is_file(self):
        return True

    def stat(self):
        import os
        return os.stat(self.path)

class _Scan(list):

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

@intent('INT-FC-R110')
def test_one_prune_pass_reclaims_every_expired_run_whatever_the_scan_order(tmp_path, monkeypatch, caplog):
    """A scan that meets each log before its record still reclaims every expired run in one
    pass, with no cleanup failure logged."""
    import os
    import time
    from orchestrator.adapters.outbound.archives import file_run_log_store as module
    old = time.time() - 40 * 86400
    order = []
    for n in range(5):
        for name in (f'run-{n}.log', f'run-{n}.log.json'):
            (tmp_path / name).write_text('{}', encoding='utf-8')
            order.append(_LazyEntry(tmp_path / name))
        os.utime(tmp_path / f'run-{n}.log', (old, old))
    monkeypatch.setattr(module.os, 'scandir', lambda root: _Scan(order))
    module.FileRunLogStore(root=str(tmp_path)).save('new', 'tail', prune_after_seconds=30 * 86400)
    assert sorted(os.listdir(tmp_path)) == ['new.log']
    assert 'Run log retention cleanup failed' not in caplog.text

@intent('INT-FC-R110')
def test_a_record_reclaimed_after_the_scan_listed_it_is_skipped_by_the_read(tmp_path, monkeypatch):
    """A prune running beside a tick may reclaim a record the read already listed; the read
    passes over it and serves every other record."""
    from orchestrator.adapters.outbound.archives import file_run_log_store as module
    from orchestrator.domain.model.execution_graph import ExecutionGraph
    from orchestrator.domain.model.retained_execution import RetainedExecution
    from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
    store = module.FileRunLogStore(root=str(tmp_path))
    kept = RetainedExecution(RunInventoryEntry('live:workflow/kept', 'kept', 'Succeeded'), ExecutionGraph('Succeeded'))
    store.save_metadata('kept', kept)
    listed = [_LazyEntry(tmp_path / 'gone.log.json'), _LazyEntry(tmp_path / 'kept.log.json')]
    monkeypatch.setattr(module.os, 'scandir', lambda root: _Scan(listed))
    assert store.all_metadata() == [kept]

@intent('INT-FC-R105')
def test_resume_refuses_an_unsigned_gate_reading_the_world_not_the_cache():
    """Resume of a delivery run parked on a gate reads the WORLD: an unsigned gate
    refuses (naming Sign), even while the warm index still carries the stale pre-push
    state - the exact window where the live cockpit funneled an operator into Resume.
    A signed gate's release proceeds (the fallback for a signed-but-stuck run), an
    unresolvable delivery-named run refuses (never release a gate blind), and a
    maintenance run is untouched."""
    import pytest
    from dataclasses import replace
    from orchestrator.domain.exceptions.conflict import Conflict
    from orchestrator.adapters.outbound.memory.index import DeliveryIndex
    from orchestrator.domain.services.delivery_resolution import derive_from_records
    PENDING = '---\nphase: scope\nstatus: gate\ngate: proposal\nsigned: pending\nreviewed: 2026-07-23\n---\nbody'
    SIGNED = PENDING.replace('signed: pending', 'signed: 2026-07-23').replace('status: gate', 'status: complete')

    class Runner(FakeRunner):

        def __init__(self):
            self.released = []

        def metadata_of(self, handle):
            from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
            repository = 'example-org/ghost' if 'ghost' in handle else 'example-org/acme'
            kind = 'maintenance' if '/maint-' in handle else 'delivery'
            return WorkflowMetadata(repository, 'v1', handle, kind, 'delivery/current')

        def resume(self, handle, *, expected_version=None):
            self.released.append(handle)
            return 'resumed:1'

    class Source:

        def __init__(self, text):
            self.text = text

        def scan(self):
            return [derive_from_records('example-org/acme', True, record_inputs({}))]

        def state_of(self, repo):
            return replace(derive_from_records(repo, 'ghost' not in repo, record_inputs({'proposal.md': self.text})), scratch_ref='delivery/current')

    def build(text):
        runner, index, source = (Runner(), DeliveryIndex(), Source(text))
        index.refresh(source)
        return (make_capabilities(FakeRepos(), workflows=runner, index=index, source=source), runner)
    svc, runner = build(PENDING)
    with pytest.raises(Conflict, match='unsigned'):
        svc.resume_run.execute('live:workflow.argoproj.io/delivery-acme-abc', **command_kwargs('example-org/*'))
    assert runner.released == []
    svc, runner = build(SIGNED)
    assert svc.resume_run.execute('live:workflow.argoproj.io/delivery-acme-abc', **command_kwargs('example-org/*'))['resumed'] == 'resumed:1'
    assert runner.released == ['live:workflow.argoproj.io/delivery-acme-abc']
    with pytest.raises(Conflict, match='current delivery'):
        svc.resume_run.execute('live:workflow.argoproj.io/delivery-ghost-zzz', **command_kwargs('example-org/*'))
    svc, runner = build(PENDING)
    assert svc.resume_run.execute('live:workflow.argoproj.io/maint-resolve-acme-ab1', **command_kwargs('example-org/*'))['resumed'] == 'resumed:1'

@intent('INT-FC-R156')
def test_a_run_row_names_the_gate_it_is_parked_on():
    """The row says WHICH gate waits, not only that one does: the sign compares it against
    the gate it just signed, so a run parked on a gate the line has passed is never
    released. A run parked on nothing carries None."""
    parked = parse_runs({'items': [WF_ONE]})[0]
    assert parked.phase == 'Suspended' and parked.parked_gate == 'proposal'
    running = parse_runs({'items': [{'metadata': {'name': 'delivery-acme-abc'}, 'status': {'phase': 'Running', 'nodes': {}}}]})[0]
    assert running.parked_gate is None


@intent('INT-FC-R182')
def test_a_steps_refusal_output_rides_the_graph_node():
    from orchestrator.adapters.inbound.http.mappers.execution import graph_dto
    wf = {'metadata': {'name': 'delivery-acme-abc'}, 'status': {'phase': 'Failed', 'nodes': {
        'n1': {'id': 'n1', 'displayName': 'design(0)', 'type': 'Pod', 'phase': 'Failed', 'templateName': 'worker-design',
               'message': 'Error (exit code 1)',
               'outputs': {'exitCode': '1', 'parameters': [
                   {'name': 'refusal', 'value': 'worker: the design stamp exited 2 without a refusal line\n'}]}},
        'n2': {'id': 'n2', 'displayName': 'scope(0)', 'type': 'Pod', 'phase': 'Succeeded', 'templateName': 'worker-scope',
               'outputs': {'parameters': [{'name': 'refusal', 'value': ''}]}},
        'n3': {'id': 'n3', 'displayName': 'gate-proposal', 'type': 'Suspend', 'phase': 'Succeeded'},
    }}}
    nodes = {n.node_id: n for n in parse_graph(wf).nodes}
    # The worker's own words, trimmed; an empty output and a node with none both read None.
    assert nodes['n1'].refusal == 'worker: the design stamp exited 2 without a refusal line'
    assert nodes['n2'].refusal is None and nodes['n3'].refusal is None
    dto = {n['id']: n for n in graph_dto(parse_graph(wf))['nodes']}
    assert dto['n1']['refusal'] == nodes['n1'].refusal
