from delivery_fixtures import record_inputs

"""Executor progression and retry policy use the compiled production workflow."""
from dataclasses import replace

from pytest_intent import intent

from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.services.delivery_resolution import derive_from_records
from orchestrator.domain.services.run_policy import _DEGRADED_EXIT


def workflow(mode, max_attempts=3):
    state = replace(derive_from_records('org/app', True, record_inputs({})), scratch_ref='delivery/current')
    return compile_workflow('org/app', state, RunConfig('token', 'org/app', True, mode), run_id='run', max_attempts=max_attempts)

@intent('INT-FC-R17')
def test_downstream_workers_are_sequential_and_do_not_continue_after_failure():
    compiled = workflow(RunMode.INTERACTIVE)
    line = next(template for template in compiled['spec']['templates'] if template['name'] == 'line')
    assert all(len(group) == 1 for group in line['steps'])
    assert all('continueOn' not in step for group in line['steps'] for step in group)
    assert [step['template'] for group in line['steps'] for step in group][:4] == ['worker-scope', 'gate-proposal', 'worker-design', 'gate-design']

@intent('INT-FC-R18')
def test_only_interactive_workflows_insert_human_gate_steps():
    def gate_steps(compiled):
        line = next(template for template in compiled['spec']['templates'] if template['name'] == 'line')
        return [step for group in line['steps'] for step in group if step['name'].startswith('gate-')]
    interactive = workflow(RunMode.INTERACTIVE)
    one_shot = workflow(RunMode.ONE_SHOT)
    assert any('suspend' in template for template in interactive['spec']['templates'])
    assert gate_steps(interactive) and all('when' not in step for step in gate_steps(interactive))
    assert not any('suspend' in template for template in one_shot['spec']['templates'])
    assert gate_steps(one_shot) == []

@intent('INT-FC-R19')
def test_executor_budget_is_bounded_and_degraded_stops_are_terminal():
    compiled = workflow(RunMode.ONE_SHOT, max_attempts=2)
    workers = [template for template in compiled['spec']['templates'] if 'container' in template]
    assert workers
    for worker in workers:
        assert worker['retryStrategy']['limit'] == 2
        assert worker['retryStrategy']['retryPolicy'] == 'Always'
        assert f"lastRetry.exitCode != '{_DEGRADED_EXIT}'" in worker['retryStrategy']['expression']
        assert worker['activeDeadlineSeconds'] > 0
