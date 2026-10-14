import { contractFixture } from './contract-fixture';
import { expect, test, type Page } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// INT-FC-R141: a finished or running run says WHO ran each step. The run row carries the
// catalog agents its workers were compiled for, each node of the graph carries the agent its
// template ran as, and a gate suspend names nobody. A run compiled before the catalog existed
// reports no agents rather than a guess.

const PHASES = ['scope', 'design', 'intent+plan', 'build+ship', 'learn'].map((name, i) => ({
    name,
    question: `Q${i}`,
    skill: 'some-skill',
    studio: null,
    gate: name === 'learn' ? null : ['proposal', 'design', 'plan', 'delivery'][i],
    gate_signed_on: i < 1 ? '2026-08-02' : null,
    record: name === 'learn' ? null : `${name}.md`,
    record_present: i < 1,
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
    records_present: ['scope.md'],
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

const run = (id: string, agents?: string[]) => ({
    kind: 'delivery',
    repo: 'example-org/acme-widget',
    handle: `live:argo/delivery-acme-widget-${id}`,
    name: `delivery-acme-widget-${id}`,
    run_id: id,
    mode: 'interactive',
    phase: 'Suspended',
    stop: null,
    created: '2026-08-22T10:00:00Z',
    started: '2026-08-22T10:00:00Z',
    finished: null,
    progress: '1/2',
    ...(agents ? { agents } : {}),
});

const RUNS = [run('lwptr', ['architect', 'designer']), run('old01')];

const GRAPH = {
    name: RUNS[0].name,
    phase: 'Suspended',
    stop: null,
    progress: '1/2',
    nodes: [
        {
            id: 'n1',
            name: 'scope',
            type: 'Pod',
            phase: 'Succeeded',
            template: 'worker-scope',
            agent: 'architect',
            message: 'ok',
            exitCode: '0',
            children: ['n2'],
            startedAt: '2026-08-22T10:00:00Z',
            finishedAt: '2026-08-22T10:20:00Z',
            artifacts: [],
        },
        {
            id: 'n2',
            name: 'gate-proposal',
            type: 'Suspend',
            phase: 'Suspended',
            template: 'gate-proposal',
            agent: null,
            message: null,
            exitCode: null,
            children: [],
            startedAt: '2026-08-22T10:20:00Z',
            finishedAt: null,
            artifacts: [],
        },
    ],
};

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
                return body(GRAPH);
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

const row = (page: Page, id: string) => page.getByRole('button', { name: new RegExp(`run ${id}`) });

test.describe('the run band says who ran each step (INT-FC-R141)', () => {
    intent('INT-FC-R141', 'the run row names the agents its steps ran as, in order', async ({ page }) => {
        await openBand(page);
        await expect(row(page, 'lwptr')).toContainText('architect → designer');
    });

    intent('INT-FC-R141', 'each worker node names its agent; a gate names nobody', async ({ page }) => {
        await openBand(page);
        // Unfold the current run so its node chips render; the band's chips, not the
        // delivery line's phase cards, are what carry the agent.
        const current = row(page, 'lwptr');
        if (!(await current.textContent())?.includes('▾')) {
            await current.click();
        }
        const scope = page.getByRole('button', { name: /scope[\s\S]*Succeeded/ }).first();
        await expect(scope).toContainText('architect');
        const gate = page.getByRole('button', { name: /gate-proposal/ }).first();
        await expect(gate).not.toContainText('architect');
        await scope.click();
        await expect(page.getByText('agent', { exact: true })).toBeVisible();
        await expect(page.locator('dd[title*="catalog agent"]')).toHaveText('architect');
    });

    intent('INT-FC-R141', 'a run from before the catalog reports no agents, not a guess', async ({ page }) => {
        await openBand(page);
        await expect(row(page, 'old01')).not.toContainText('→');
        await expect(row(page, 'old01')).not.toContainText('architect');
    });
});
