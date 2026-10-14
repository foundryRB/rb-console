import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { contractFixture } from './contract-fixture';
import { expect, test, type Page } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// The reported cockpit (#181): a one-shot line whose design stamp refused four times ended its
// run Failed, and the operator opened it hours later to a phase that looked in progress and a
// run that said nothing about why. INT-FC-R182: a failed run reads failed, with the worker's own
// last refusal line beside it - the step output that outlives the pod - and falls back to the
// executor's message for a step that left none.

const PHASES = ['scope', 'design', 'intent+plan', 'build+ship', 'learn'].map((name, i) => ({
    name,
    question: `Q${i}`,
    skill: 'some-skill',
    studio: null,
    gate: name === 'learn' ? null : ['proposal', 'design', 'plan', 'delivery'][i],
    gate_signed_on: i < 1 ? '2026-10-07' : null,
    record: name === 'learn' ? null : `${name}.md`,
    record_present: i < 2,
    is_current: name === 'design',
    needs_review: false,
    artifact: null,
}));

const OVERVIEW = {
    repo: 'example-org/acme-widget',
    exists: true,
    status: 'run-phase',
    phase: 'design',
    next_skill: null,
    next_command: null,
    blocked_gate: null,
    gates: [],
    records_present: ['scope.md', 'design.md'],
    learned_on: null,
    config: {
        mode: 'one-shot',
        provider: 'claude',
        base_url: '',
        model: 'claude-opus-5',
        agent: 'my-claude',
        timeout_hours: 1,
        credentialed: true,
    },
    phases: PHASES,
};

const RUN = JSON.parse(
    execFileSync(
        process.env.PYTHON ?? 'python',
        [path.resolve('e2e/compiled_runs_fixture.py'), OVERVIEW.repo, 'd-16af0', 'Failed', 'delivery', 'resolve', '7', 'gated'],
        { encoding: 'utf8' },
    ),
);

const REFUSAL = 'worker: fresh-eyes review did not pass the design gate for design (.delivery/reviews/design-r3.md: VERDICT: FAIL)';

const node = (id: string, phase: string, extra: Record<string, unknown> = {}) => ({
    id,
    name: `design(${id})`,
    type: 'Pod',
    phase,
    template: 'worker-design',
    agent: null,
    message: null,
    exitCode: phase === 'Failed' ? '1' : '0',
    children: [],
    startedAt: `2026-10-07T04:0${id}:00Z`,
    finishedAt: `2026-10-07T04:1${id}:00Z`,
    artifacts: [],
    ...extra,
});

async function openCockpit(
    page: Page,
    nodes: unknown[],
    { overview = OVERVIEW, run = RUN, graphPhase = 'Failed' }: { overview?: typeof OVERVIEW; run?: typeof RUN; graphPhase?: string } = {},
) {
    await page.route('**/api/**', async (route) => {
        const pathname = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [run])) });
        switch (pathname) {
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(overview);
            case '/deliveries/config':
                return body(overview.config);
            case '/runs':
                return body({ runs: [run] });
            case '/runs/graph':
                return body({ name: run.name, phase: graphPhase, stop: null, progress: '1/2', nodes });
            case '/fleet':
                return body({ projects: [] });
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({ agents: [] });
            case '/deliveries/plan':
                return body({ kind: 'await-gate', gate: overview.blocked_gate, launch: null, state: contractFixture(overview, [run]) });
            default:
                return body({});
        }
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/d?repo=example-org%2Facme-widget');
}

test.describe('a failed run says why (INT-FC-R182)', () => {
    intent('INT-FC-R182', "a failed run names its last step's refusal line", async ({ page }) => {
        await openCockpit(page, [
            node('1', 'Failed', { refusal: 'worker: an earlier attempt', message: 'Error (exit code 1)' }),
            node('2', 'Failed', { refusal: REFUSAL, message: 'Error (exit code 1)' }),
        ]);
        const refusal = page.getByTestId('run-refusal');
        await expect(refusal).toHaveText(REFUSAL);
        await expect(refusal).toHaveClass(/destructive/);
    });

    intent('INT-FC-R182', 'a step that left no refusal falls back to the executor message', async ({ page }) => {
        await openCockpit(page, [node('1', 'Failed', { message: 'Error (exit code 1)' })]);
        await expect(page.getByTestId('run-refusal')).toHaveText('Error (exit code 1)');
    });

    intent('INT-FC-R182', 'a run the Console stopped carries no refusal', async ({ page }) => {
        await openCockpit(page, [node('1', 'Failed', { message: 'Stopped with strategy: Stop', refusal: 'worker: x' })]);
        await expect(page.getByTestId('run-refusal')).toHaveCount(0);
    });
});

// A one-shot line whose design stamp refused over a passing review (INT-FC-R181): its run ended on
// the stamp-refused stop and the record waits at its gate. Sign closes the gate and a drive takes the
// line on; a Sign releases a run only where one is parked on the gate.
const AWAITING = {
    ...OVERVIEW,
    status: 'awaiting-gate',
    next_command: 'sign the design gate (the one-shot stamp refused: REFUSED: export refused)',
    blocked_gate: 'design',
};

const PARKED_RUN = JSON.parse(
    execFileSync(
        process.env.PYTHON ?? 'python',
        [path.resolve('e2e/compiled_runs_fixture.py'), OVERVIEW.repo, 'd-16af1', 'Suspended', 'delivery', 'resolve', '7', 'gated'],
        { encoding: 'utf8' },
    ),
);

const STAMP_REFUSED =
    'worker: the design stamp refused over a passing review (REFUSED: export refused) - stamp-refused stop, not retrying (exit 68); sign the design gate from the cockpit, then drive the line';

const STOPPED_NODES = [node('1', 'Failed', { refusal: STAMP_REFUSED, message: 'Error (exit code 68)', exitCode: '68' })];

test.describe('a refused one-shot stamp leaves the line signable (INT-FC-R181)', () => {
    intent('INT-FC-R181', 'the gate card offers Sign, then a drive, beside the stopped run', async ({ page }) => {
        await openCockpit(page, STOPPED_NODES, { overview: AWAITING });
        await expect(page.getByTestId('run-refusal')).toHaveText(STAMP_REFUSED);
        const hint = page.getByTestId('gate-card-hint');
        await expect(hint).toContainText('Signing stamps today into the record and closes the gate; then drive the line on.');
        await expect(hint).not.toContainText('releases the next phase');
        await expect(page.getByRole('button', { name: 'Sign the design gate', exact: true }).first()).toBeVisible();
    });
});

// What a Sign does, said wherever it is offered: it releases a run parked on the gate, and on a line
// whose run has ended it closes the gate for a drive to take the line on.
const PARKED = {
    overview: { ...AWAITING, next_command: 'sign the design gate', config: { ...OVERVIEW.config, mode: 'interactive' } },
    run: PARKED_RUN,
    graphPhase: 'Suspended',
};

test.describe('the cockpit says what a Sign does', () => {
    test('a run parked on the gate is the one a Sign releases', async ({ page }) => {
        await openCockpit(page, [], PARKED);
        await expect(page.getByTestId('gate-card-hint')).toContainText(
            'Signing stamps today into the record and releases the next phase',
        );
    });

    test('the dry run on a stopped line names a Sign that closes the gate, then a drive', async ({ page }) => {
        await openCockpit(page, STOPPED_NODES, { overview: AWAITING });
        await page.getByRole('button', { name: 'Plan · dry run' }).click();
        const hint = page.getByTestId('action-gate-hint');
        await expect(hint).toHaveText('Awaiting the design gate. Sign it to close the gate, then drive the line on.');
    });

    test('the dry run on a parked run names the suspend a Sign releases', async ({ page }) => {
        await openCockpit(page, [], PARKED);
        await page.getByRole('button', { name: 'Plan · dry run' }).click();
        const hint = page.getByTestId('action-gate-hint');
        await expect(hint).toHaveText('Suspended on the design gate. Sign it to release the next phase.');
    });
});
