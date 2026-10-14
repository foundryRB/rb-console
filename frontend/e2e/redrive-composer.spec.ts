import { contractFixture } from './contract-fixture';
import { expect, test, type Page } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// Pressing Re-drive does not re-drive: it opens the composer that does, and that composer
// lives in the CONSOLE card - the right column of the grid BELOW the line card. On the one
// line that most needs it (degraded, its run band unfolded, its record open) the console
// sits a screen down, and below lg it is not rendered at all while the workspace holds the
// pane tab. So the degraded banner's own call-to-action - the control its prose sends the
// operator to - opened a panel they could not see: no error, no progress, nothing. The
// reported cockpit was alexandria, Build+Ship degraded, "nothing happens at all".
//
// INT-FC-R121: every Re-drive surface makes the composer it opened visible from where it
// was pressed. The composer's own submit is unchanged and still the act.

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
    status: 'degraded',
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

const RUN = {
    kind: 'delivery',
    repo: 'example-org/acme-widget',
    handle: 'live:argo/delivery-acme-widget-c2ghj',
    name: 'delivery-acme-widget-c2ghj',
    run_id: 'c2ghj',
    mode: 'interactive',
    phase: 'Failed',
    created: '2026-08-10T18:57:00Z',
    started: '2026-08-10T18:57:00Z',
    finished: '2026-08-10T19:37:00Z',
    progress: '0/1',
};

async function stubApi(page: Page) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [RUN])) });
        switch (path) {
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(OVERVIEW);
            case '/deliveries/config':
                return body(OVERVIEW.config);
            case '/runs':
                return body({ runs: [RUN] });
            case '/runs/graph':
                return body({ name: RUN.name, phase: 'Failed', nodes: [] });
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

/** The composer's feedback box: the thing the operator must actually reach. */
const composer = (page: Page) => page.getByPlaceholder(/What should change/);

async function openCockpit(page: Page, width: number, height = 900) {
    await stubApi(page);
    await page.setViewportSize({ width, height });
    await page.goto('/d?repo=example-org%2Facme-widget');
    await expect(page.getByRole('button', { name: /Plan · dry run/ })).toBeVisible();
    // The composer is closed until a Re-drive control opens it.
    await expect(composer(page)).toHaveCount(0);
}

// Each surface that offers a re-drive, by the name the operator reads on it.
const SURFACES = [
    { name: /↻ Re-drive build\+ship/i, label: "the degraded banner's call-to-action" },
    { name: /^↻ Re-drive$/, label: "the masthead's primary on a failed run" },
];

test.describe('a Re-drive control brings its composer to the operator (INT-FC-R121)', () => {
    for (const { name, label } of SURFACES) {
        intent('INT-FC-R121', `${label} focuses the composer on a wide viewport`, async ({ page }) => {
            // Wide: the console renders beside the workspace, but a screen down the page.
            // Focus is what proves the operator was actually taken there - without it the
            // composer opens silently below the fold and the button reads as dead.
            await openCockpit(page, 1280);
            await page.getByRole('button', { name }).first().click();
            await expect(composer(page)).toBeFocused();
            await expect(composer(page)).toBeInViewport();
        });

        intent('INT-FC-R121', `${label} reveals the composer below lg, where the console is a tab`, async ({ page }) => {
            // Below lg only ONE pane renders, and it defaults to the workspace - so the
            // composer was display:none and no amount of scrolling would have found it.
            await openCockpit(page, 900);
            await page.getByRole('button', { name }).first().click();
            await expect(composer(page)).toBeVisible();
        });
    }

    intent('INT-FC-R121', 'the composer names the phase it will re-drive, and still submits the act itself', async ({ page }) => {
        // Opening is not driving: the composer's own button is the act, and it carries the
        // operator's feedback verbatim. Pinned so "make it visible" never becomes "fire it".
        await openCockpit(page, 1280);
        const posted: unknown[] = [];
        await page.route('**/api/deliveries/drive', async (route) => {
            posted.push(route.request().postDataJSON());
            return route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ state: OVERVIEW, run: null, launched: true }),
            });
        });

        await page.getByRole('button', { name: /↻ Re-drive build\+ship/i }).first().click();
        await expect(page.getByText(/Re-drive ·/)).toBeVisible();
        expect(posted, 'opening the composer must not drive anything').toHaveLength(0);

        await composer(page).fill('The onboarding PR never merged; retry the admit step.');
        await page.getByRole('button', { name: /Re-drive with this feedback/ }).click();
        await expect.poll(() => posted).toHaveLength(1);
        expect(posted[0]).toMatchObject({
            target: 'example-org/acme-widget',
            from_phase: 'build+ship',
            feedback: 'The onboarding PR never merged; retry the admit step.',
        });
    });
});
