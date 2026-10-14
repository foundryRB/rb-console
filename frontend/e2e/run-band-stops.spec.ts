import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { contractFixture } from './contract-fixture';
import { expect, test, type Page } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// The reported cockpit: a delivery iterated on across two weeks, its run band a wall of eight
// consecutive red "Failed" rows - every one of them a run the CONSOLE had stopped on the
// operator's own next drive. Argo has no phase for a deliberate close (a shutdown lands in
// Failed), so the executor's word was passed through unedited, and the band ended up
// contradicting its own contents: unfolding any of those rows showed steps reading "Stopped".
//
// INT-FC-R124: the Console marks WHO stopped a run and derives the phase from its own mark.
// The band then says Stopped (amber) for a deliberate close and keeps Failed (red) for a run
// that genuinely died - while `· superseded` stays what it always was, the positional fact
// that this is not the newest run.

const PHASES = ['scope', 'design', 'intent+plan', 'build+ship', 'learn'].map((name, i) => ({
    name,
    question: `Q${i}`,
    skill: 'some-skill',
    studio: null,
    gate: name === 'learn' ? null : ['proposal', 'design', 'plan', 'delivery'][i],
    gate_signed_on: i < 3 ? '2026-08-02' : null,
    record: name === 'learn' ? null : `${name}.md`,
    record_present: i < 3,
    is_current: name === 'build+ship',
    needs_review: false,
    artifact: null,
}));

const OVERVIEW = {
    repo: 'example-org/acme-widget',
    exists: true,
    status: 'run-phase',
    phase: 'build+ship',
    next_skill: null,
    next_command: null,
    blocked_gate: null,
    gates: [],
    records_present: ['scope.md', 'design.md', 'handoff.md'],
    learned_on: null,
    config: {
        mode: 'interactive',
        provider: 'claude',
        base_url: '',
        model: 'claude-opus-5',
        agent: 'my-claude',
        timeout_hours: 1,
        credentialed: true,
    },
    phases: PHASES,
};

const run = (id: string, phase: string, stop: string | null, repo = OVERVIEW.repo, kind = 'delivery') => ({
    ...JSON.parse(
        execFileSync(
            process.env.PYTHON ?? 'python',
            [path.resolve('e2e/compiled_runs_fixture.py'), repo, `d-${id}`, phase, kind, 'resolve', '7', 'gated'],
            { encoding: 'utf8' },
        ),
    ),
    stop,
});

// Newest first, exactly as the executor lists them. Rows 1..3 are the history: two the
// Console closed on a re-drive, one that failed on its own before any of it.
const RUNS = [
    run('promoted', 'Running', null, OVERVIEW.repo, 'promotion'),
    run('maintained', 'Running', null, OVERVIEW.repo, 'maintenance'),
    run('foreign', 'Running', null, 'other-org/acme-widget'),
    run('lwptr', 'Running', null),
    run('c2ghj', 'Stopped', 'superseded'),
    run('lqp8z', 'Stopped', 'superseded'),
    run('7hxk9', 'Failed', null),
];

async function openBand(page: Page) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, RUNS)) });
        switch (path) {
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(OVERVIEW);
            case '/deliveries/config':
                return body(OVERVIEW.config);
            case '/runs':
                return body({ runs: RUNS });
            case '/runs/graph':
                return body({ name: RUNS.find((r) => r.run_id === 'd-lwptr')?.name, phase: 'Running', stop: null, nodes: [] });
            case '/fleet':
                return body({ projects: [] });
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({ agents: [] });
            default:
                return body({});
        }
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/d?repo=example-org%2Facme-widget');
    await page.getByRole('button', { name: /Show the run band|⌄/ }).first().click();
}

/** One band row, by the short run id it is labelled with. */
const row = (page: Page, id: string) => page.getByRole('button', { name: new RegExp(`run ${id}`) });

test.describe('the run band names a stop as a stop (INT-FC-R124)', () => {
    intent('INT-FC-R124', 'a run the Console superseded reads Stopped, not Failed', async ({ page }) => {
        await openBand(page);
        // The pain, directly: these rows used to read "Failed" for a close the Console itself
        // performed. Neither may claim the run failed.
        await expect(row(page, 'c2ghj')).toContainText('Stopped');
        await expect(row(page, 'c2ghj')).not.toContainText('Failed');
        await expect(row(page, 'lqp8z')).toContainText('Stopped');
    });

    intent('INT-FC-R124', 'a deliberate close is amber; only a real failure is red', async ({ page }) => {
        await openBand(page);
        const colour = (id: string, text: string) =>
            row(page, id).locator('span', { hasText: new RegExp(`^${text}$`) }).first();
        // Amber (the node inspector's own treatment for the same event) vs destructive red.
        // Colour is the whole point: eight red rows read as eight things gone wrong.
        await expect(colour('c2ghj', 'Stopped')).toHaveClass(/amber/);
        await expect(colour('7hxk9', 'Failed')).toHaveClass(/destructive/);
    });

    intent('INT-FC-R124', 'superseded stays the relation, on a stopped row and a failed one alike', async ({ page }) => {
        await openBand(page);
        // `· superseded` answers WHERE a run sits (not the newest), not HOW it ended - so it
        // rides on the run that failed on its own exactly as it does on the stopped ones, and
        // the newest run carries neither it nor a stop.
        await expect(row(page, 'c2ghj')).toContainText('superseded');
        await expect(row(page, '7hxk9')).toContainText('superseded');
        await expect(row(page, '7hxk9')).toContainText('Failed');
        await expect(row(page, 'lwptr')).not.toContainText('superseded');
    });

    intent('INT-FC-R124', 'the row says who stopped it', async ({ page }) => {
        await openBand(page);
        await expect(row(page, 'c2ghj').locator('[title*="newer drive"]')).toHaveCount(1);
    });
});

test('compiled run identities retain this repository history and exclude a colliding slug', async ({
    page,
}) => {
    const requests: string[] = [];
    page.on('request', (request) => {
        if (request.url().includes('/runs/graph'))
            requests.push(new URL(request.url()).searchParams.get('handle') ?? '');
    });
    await openBand(page);
    await expect(row(page, 'lwptr')).toBeVisible();
    await expect(row(page, 'c2ghj')).toBeVisible();
    await expect(row(page, 'foreign')).toHaveCount(0);
    await expect(row(page, 'promoted')).toHaveCount(0);
    await expect(row(page, 'maintained')).toHaveCount(0);
    await expect.poll(() => requests).toContain('live:workflow.argoproj.io/d-lwptr');
    expect(requests).not.toContain('live:workflow.argoproj.io/d-foreign');
});
