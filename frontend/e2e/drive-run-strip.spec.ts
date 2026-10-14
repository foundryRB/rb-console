import { contractFixture } from './contract-fixture';
import { expect, type Page } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// A drive on a line with no run the cockpit knows about showed the "drive submitted" panel and
// never the run strip: the page read the runs once, straight after the drive answered, before
// the executor listed the new workflow, and the live poll only runs once a run is known. The
// strip came back only on a reload (#179).
//
// INT-FC-R191: after a drive the cockpit follows the run up on the sign's short cadence.

const PHASES = ['scope', 'design', 'intent+plan', 'build+ship', 'learn'].map((name, i) => ({
    name,
    question: `Q${i}`,
    skill: 'some-skill',
    studio: null,
    gate: name === 'learn' ? null : ['proposal', 'design', 'plan', 'delivery'][i],
    gate_signed_on: i < 2 ? '2026-08-02' : null,
    record: name === 'learn' ? null : `${name}.md`,
    record_present: i < 2,
    is_current: name === 'intent+plan',
    needs_review: false,
    artifact: null,
}));

const OVERVIEW = {
    repo: 'example-org/acme-widget',
    exists: true,
    status: 'run-phase',
    phase: 'intent+plan',
    next_skill: null,
    next_command: null,
    blocked_gate: null,
    gates: [],
    records_present: ['scope.md', 'design.md'],
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

const RUN = {
    kind: 'delivery',
    repo: 'example-org/acme-widget',
    handle: 'live:workflow.argoproj.io/d-3c2900f6322a',
    name: 'd-3c2900f6322a',
    run_id: 'd-3c2900f6322a',
    mode: 'interactive',
    phase: 'Running',
    created: '2026-10-08T15:33:00Z',
    started: '2026-10-08T15:33:00Z',
    finished: null,
    progress: '0/1',
};

async function stubApi(page: Page, listed: () => boolean) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const runs = listed() ? [RUN] : [];
        const body = (data: unknown) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(contractFixture(data, runs)),
            });
        switch (path) {
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(OVERVIEW);
            case '/deliveries/config':
                return body(OVERVIEW.config);
            case '/deliveries/drive':
                return body({ handle: RUN.handle, run_id: RUN.run_id, state: OVERVIEW, steps: [] });
            case '/runs':
                return body({ runs });
            case '/runs/graph':
                return body({ name: RUN.name, phase: 'Running', nodes: [] });
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
}

intent(
    'INT-FC-R191',
    'a drive whose first runs read is empty still shows the run strip without a reload',
    async ({ page }) => {
        // The executor lists the new workflow only a few seconds after the drive answers.
        let drivenAt = 0;
        await stubApi(page, () => drivenAt > 0 && Date.now() - drivenAt > 1500);
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/d?repo=example-org%2Facme-widget');
        await expect(page.getByRole('button', { name: /Plan · dry run/ })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Terminate' })).toHaveCount(0);

        drivenAt = Date.now();
        await page.getByRole('button', { name: /Drive/ }).first().click();

        await expect(page.getByRole('button', { name: 'Terminate' })).toBeVisible({
            timeout: 10_000,
        });
        await expect(page.getByText(/run 3c2900f6322a/).first()).toBeVisible();
    },
);
