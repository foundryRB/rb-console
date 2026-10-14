import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';

// The fleet Inbox strip, driven against the stubbed /api layer. It pins the reshape from a
// "Maintenance inbox" that linked every row to one repo backlog into an "Inbox" whose rows link
// per signal: a ticket deep-links into the Console (the Maintenance line at that ticket), every
// other signal opens its own artifact (the PR, the checks, ArgoCD, the unreleased commits). Plus
// the project/signal filters the growing fleet needs.

const OVERVIEW = {
    repo: 'example-org/acme-widget',
    exists: true,
    status: 'run-phase',
    phase: 'build+ship',
    next_skill: null,
    next_command: null,
    blocked_gate: null,
    gates: [],
    records_present: [],
    config: { mode: 'interactive', provider: 'claude', base_url: '', model: 'sonnet', agent: 'my-claude', credentialed: true },
    phases: [],
};

const MAINT_STATE = {
    repo: 'example-org/acme-widget',
    positions: {
        repo: 'example-org/acme-widget',
        issues: [
            { number: 5, title: 'PT-PT audio labels', author: 'rafaelgpires', labels: [], url: 'https://x/5', created_at: '' },
            { number: 7, title: 'Fix the thing', author: 'rafaelgpires', labels: [], url: 'https://x/7', created_at: '' },
        ],
        prs: [],
        train: { version: '2.10.3', unreleased_total: 2, breaking: 0, feat: 1, fix: 1, other: 0, next_version: '2.11.0', deployed: '', healthy: null },
    },
    action: { acts: ['resolve', 'review', 'reconcile-docs'], modes: ['gated', 'one-shot', 'direct'], default_mode: 'gated' },
    delivery: { status: 'run-phase', phase: 'build+ship' },
    driven: [],
};

// One of each signal, across two repos, so the taxonomy and the per-repo filter are both exercised.
// #5 carries no stage (a freshly-filed ticket, no PR yet); #7 is a running job's own row - the
// issue #9 fix this pins: the ticket's loop stage rides alongside its signal, not just the PR row.
const INBOX = [
    { repo: 'example-org/acme-widget', signal: 'red-ci', detail: 'PR #14 checks red: feat(x)', act: 'investigate', number: 14, ts: '2026-07-10T10:00:00Z', stage: '' },
    { repo: 'example-org/acme-widget', signal: 'drift', detail: 'deployment unhealthy at 2.10.3', act: 'investigate', number: null, ts: '', stage: '' },
    { repo: 'example-org/other-app', signal: 'pr-review', detail: 'PR #16 awaits review: chore(catalog)', act: 'review', number: 16, ts: '2026-07-01T10:00:00Z', stage: '' },
    { repo: 'example-org/acme-widget', signal: 'unreleased', detail: '2 unreleased commit(s); next would cut 2.11.0', act: 'release', number: null, ts: '', stage: '' },
    { repo: 'example-org/acme-widget', signal: 'issue', detail: '#5 PT-PT audio labels', act: 'resolve', number: 5, ts: '2026-07-12T10:00:00Z', stage: 'open' },
    { repo: 'example-org/acme-widget', signal: 'running', detail: 'review PR #12 for #7 in progress: Fix the thing', act: 'watch', number: 7, ts: '', stage: 'in-progress' },
];

// Prepare pure contract projections before browser assertions start their timeout.
contractFixture(OVERVIEW, []);
contractFixture(MAINT_STATE, []);

async function stubApi(page: Page) {
    await page.route('**/api/**', async (route) => {
        const u = new URL(route.request().url());
        const path = u.pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        switch (path) {
            case '/fleet':
                return body({ projects: [] });
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({ agents: [{ name: 'my-claude', provider: 'claude', base_url: '', model: 'sonnet', models: ['sonnet'], configured: true }] });
            case '/maintenance/inbox':
                return body({ items: INBOX, scanned: true });
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(OVERVIEW);
            case '/deliveries/config':
                return body(OVERVIEW.config);
            case '/maintenance/state':
                return body(MAINT_STATE);
            case '/runs':
                return body({ runs: [] });
            case '/maintenance/substance':
                return body({ kind: 'issue', number: 5, title: 'PT-PT audio labels', body: 'Body of #5', url: 'https://x/5' });
            default:
                return body({});
        }
    });
}

const inboxLink = (page: Page, detail: RegExp) => page.getByRole('link', { name: detail });

/** Pick a sort order through the dropdown the row actually renders: open the trigger, click the
 * radio. Click, not check() - the panel dismisses itself on the pick, so the radio is gone before
 * check() could confirm its state. It closing is what lets consecutive calls compose. */
async function sortBy(page: Page, order: string) {
    await page.getByRole('button', { name: 'Sort the inbox' }).click();
    await page.getByRole('radio', { name: `by ${order}` }).click();
}

test.describe('the fleet Inbox', () => {
    test.beforeEach(async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/');
        await expect(page.getByText('Inbox', { exact: true })).toBeVisible();
    });

    test('it is named Inbox, not Maintenance inbox, and counts every signal', async ({ page }) => {
        await expect(page.getByText('Maintenance inbox')).toHaveCount(0);
        await expect(page.getByText('6 item(s)')).toBeVisible();
    });

    test('a row carries the maintenance stage as its own column (#9)', async ({ page }) => {
        // The ticket #5 row shows it is a freshly-filed ticket, no PR yet.
        const issueRow = inboxLink(page, /#5 PT-PT audio labels/);
        await expect(issueRow.getByText('open', { exact: true })).toBeVisible();
        // The running row for #7 shows a job is working it right now - not just the pulsing
        // "running" signal badge, its own stage column reads the same, unambiguously. Its
        // detail names both numbers and which namespace each is in (INT-FC-R98), so the
        // operator can join a review to the ticket it is reviewing without a click.
        const runningRow = inboxLink(page, /review PR #12 for #7 in progress/);
        await expect(runningRow.getByText('in progress', { exact: true })).toBeVisible();
        // and it deep-links at the TICKET, never at the PR number the review act targets
        await expect(runningRow).toHaveAttribute('href', '/d?repo=example-org%2Facme-widget&mode=maintenance&ticket=7');
    });

    test('a ticket deep-links into the Console; every other signal opens its artifact', async ({ page }) => {
        // The issue opens in-app at its ticket (SPA link, no new tab).
        const issue = inboxLink(page, /#5 PT-PT audio labels/);
        await expect(issue).toHaveAttribute('href', '/d?repo=example-org%2Facme-widget&mode=maintenance&ticket=5');
        await expect(issue).not.toHaveAttribute('target', '_blank');

        // The rest open their own artifact in a new tab.
        const pr = inboxLink(page, /PR #16 awaits review/);
        await expect(pr).toHaveAttribute('href', 'https://github.com/example-org/other-app/pull/16');
        await expect(pr).toHaveAttribute('target', '_blank');

        await expect(inboxLink(page, /PR #14 checks red/)).toHaveAttribute('href', 'https://github.com/example-org/acme-widget/pull/14/checks');
        await expect(inboxLink(page, /2 unreleased commit/)).toHaveAttribute('href', 'https://github.com/example-org/acme-widget/commits');
        // The zone is the console's own host minus its first label; served from a bare
        // `localhost` it falls back to that host, so the link stays local. It used to fall
        // back to the UPSTREAM install's zone, which pointed a dev console's every link at
        // another organisation's estate.
        await expect(inboxLink(page, /deployment unhealthy/)).toHaveAttribute('href', 'https://argocd.localhost/applications/acme-widget');
    });

    test('filtering by signal narrows the queue and clears back', async ({ page }) => {
        await page.getByRole('button', { name: 'Filter the inbox by signal' }).click();
        await page.getByRole('checkbox', { name: 'issue' }).check();
        await expect(page.getByText('1 of 6')).toBeVisible();
        await expect(inboxLink(page, /deployment unhealthy/)).toHaveCount(0);
        await expect(inboxLink(page, /#5 PT-PT audio labels/)).toBeVisible();
        await page.getByRole('button', { name: 'clear' }).click();
        await expect(page.getByText('6 item(s)')).toBeVisible();
    });

    test('filtering by project shows only that repo', async ({ page }) => {
        await page.getByRole('button', { name: 'Filter the inbox by project' }).click();
        await page.getByRole('checkbox', { name: 'other-app' }).check();
        await expect(page.getByText('1 of 6')).toBeVisible();
        await expect(inboxLink(page, /PR #16 awaits review/)).toBeVisible();
        await expect(inboxLink(page, /#5 PT-PT audio labels/)).toHaveCount(0);
    });

    test('filtering combines multiple projects and multiple signals', async ({ page }) => {
        // Two signals at once: issue + pr-review picks up rows from both repos.
        await page.getByRole('button', { name: 'Filter the inbox by signal' }).click();
        await page.getByRole('checkbox', { name: 'issue' }).check();
        await page.getByRole('checkbox', { name: 'pr-review' }).check();
        await page.locator('body').click({ position: { x: 0, y: 0 } });
        await expect(page.getByText('2 of 6')).toBeVisible();
        await expect(inboxLink(page, /#5 PT-PT audio labels/)).toBeVisible();
        await expect(inboxLink(page, /PR #16 awaits review/)).toBeVisible();
        await expect(inboxLink(page, /deployment unhealthy/)).toHaveCount(0);

        // Narrow further with a project filter: combined with the signal filter above.
        await page.getByRole('button', { name: 'Filter the inbox by project' }).click();
        await page.getByRole('checkbox', { name: 'acme-widget' }).check();
        await page.locator('body').click({ position: { x: 0, y: 0 } });
        await expect(page.getByText('1 of 6')).toBeVisible();
        await expect(inboxLink(page, /#5 PT-PT audio labels/)).toBeVisible();
        await expect(inboxLink(page, /PR #16 awaits review/)).toHaveCount(0);

        await page.getByRole('button', { name: 'clear' }).click();
        await expect(page.getByText('6 item(s)')).toBeVisible();
    });

    test('Escape closes a filter dropdown and returns focus to its trigger', async ({ page }) => {
        const trigger = page.getByRole('button', { name: 'Filter the inbox by signal' });
        await trigger.click();
        await expect(page.getByRole('checkbox', { name: 'issue' })).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('checkbox', { name: 'issue' })).toHaveCount(0);
        await expect(trigger).toBeFocused();
    });

    test('sorting reorders the queue (criticality, project, age), all computed', async ({ page }) => {
        const y = async (detail: RegExp) => (await inboxLink(page, detail).boundingBox())!.y;
        // Default is criticality (the attention order): the PR-review sits above the plain issue.
        expect(await y(/PR #16 awaits review/)).toBeLessThan(await y(/#5 PT-PT audio labels/));
        // By project: acme-widget rows sort first, so the other-app PR drops below the acme issue.
        await sortBy(page, 'project');
        expect(await y(/PR #16 awaits review/)).toBeGreaterThan(await y(/#5 PT-PT audio labels/));
        // By age (oldest first): the Jul-01 PR rises above the Jul-10 red-ci.
        await sortBy(page, 'age');
        expect(await y(/PR #16 awaits review/)).toBeLessThan(await y(/PR #14 checks red/));
    });

    // The sort control is the page's own dropdown, not a native <select>. A <select> is drawn by
    // the browser: it sized its own box (standing a few px out of line with the filter triggers
    // beside it) and opened its option list as an unthemed OS popup against the dark console. Both
    // halves are pinned here so neither can come back.
    test('the sort control shares the filter row metrics and stays in-theme when open', async ({ page }) => {
        // A native <select> reports role=combobox; this one is a trigger button like its siblings.
        await expect(page.getByRole('combobox', { name: 'Sort the inbox' })).toHaveCount(0);
        const triggers = ['Sort the inbox', 'Filter the inbox by project', 'Filter the inbox by signal'];
        const [sort, ...filters] = await Promise.all(
            triggers.map(async (n) => (await page.getByRole('button', { name: n }).boundingBox())!),
        );
        for (const f of filters) {
            expect(f.height).toBeCloseTo(sort.height, 0); // same box...
            expect(f.y).toBeCloseTo(sort.y, 0); // ...on the same baseline
        }
        // Opened, its panel is one this page renders and themes, holding all three orders.
        await page.getByRole('button', { name: 'Sort the inbox' }).click();
        for (const o of ['by criticality', 'by project', 'by age']) {
            await expect(page.getByRole('radio', { name: o })).toBeVisible();
        }
        // A sort is a terminal choice, so the panel dismisses itself on the pick and the trigger
        // reads back the new order (the filters, assembling a set, stay open instead).
        await page.getByRole('radio', { name: 'by age' }).click();
        await expect(page.getByRole('radio', { name: 'by age' })).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Sort the inbox' })).toHaveText(/by age/);
    });
});

test.describe('the Inbox on mobile', () => {
    test('a populated Inbox with its filter row does not overflow at 390px', async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto('/');
        await expect(page.getByText('Inbox', { exact: true })).toBeVisible();
        // The filters stay reachable on a phone...
        await expect(page.getByRole('button', { name: 'Filter the inbox by project' })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Filter the inbox by signal' })).toBeVisible();
        // ...and the page never scrolls sideways (the responsive invariant).
        const overflow = await page.evaluate(
            () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow).toBe(0);
    });
});

test.describe('the Inbox ticket deep-link', () => {
    test('?ticket=N opens the Maintenance cockpit at that ticket, not the backlog', async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=maintenance&ticket=5');
        // The cockpit is open (its line and the back-to-backlog control), landed straight on #5.
        await expect(page.getByRole('tablist')).toBeVisible();
        await expect(page.getByRole('button', { name: '← backlog' })).toBeVisible();
        await expect(page.getByText('#5 PT-PT audio labels')).toBeVisible();
    });
});

/** The filter panels open downward out of the strip's header, so they must be free to overhang the
 * strip. They were not: the strip clipped its own box, and the shorter the queue the fewer options
 * survived - filtered down to nothing, the panel was cut to barely one row and the projects below
 * it could not be reached at all, the operator's only way back being the header's `clear`. */
test.describe('the Inbox filter panels overhang the strip', () => {
    const REPOS = ['example-org/alpha', 'example-org/bravo', 'example-org/charlie', 'example-org/delta', 'example-org/echo', 'example-org/foxtrot'];
    const WIDE = [
        ...REPOS.map((repo, i) => ({
            repo, signal: 'issue', detail: `#${i + 1} something needs attention`,
            act: 'resolve', number: i + 1, ts: '2026-07-12T10:00:00Z', stage: 'open',
        })),
        // One row of a second signal, so a signal pick can empty the queue under a project pick.
        { repo: 'example-org/alpha', signal: 'drift', detail: 'deployment unhealthy at 1.0.0', act: 'investigate', number: null, ts: '', stage: '' },
    ];

    /** Every option's own centre must hit-test back to itself: a clipped one is painted over by
     * whatever lies below the strip, so the operator cannot click what they can see. */
    const reachable = (page: Page) =>
        page.getByRole('checkbox').evaluateAll((els) =>
            els.every((el) => {
                const r = el.getBoundingClientRect();
                return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) === el;
            }),
        );

    test('a queue filtered down to nothing still reaches every project in the panel', async ({ page }) => {
        await stubApi(page);
        await page.route('**/api/maintenance/inbox*', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: WIDE, scanned: true }) }),
        );
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/');
        await expect(page.getByText('Inbox', { exact: true })).toBeVisible();

        // Narrow the queue to a project whose only signal is 'issue'...
        await page.getByRole('button', { name: 'Filter the inbox by project' }).click();
        await page.getByRole('checkbox', { name: 'foxtrot' }).check();
        await page.keyboard.press('Escape');
        // ...then to the one signal it does not carry: the strip collapses to its emptiest.
        await page.getByRole('button', { name: 'Filter the inbox by signal' }).click();
        await page.getByRole('checkbox', { name: 'drift' }).check();
        await page.keyboard.press('Escape');
        await expect(page.getByText('No rows match this filter.')).toBeVisible();

        // Two lines of strip, six projects of panel: all six stay clickable, the last one included.
        await page.getByRole('button', { name: 'Filter the inbox by project' }).click();
        await expect(page.getByRole('checkbox')).toHaveCount(REPOS.length);
        expect(await reachable(page)).toBe(true);
        await page.getByRole('checkbox', { name: 'alpha', exact: true }).check();
        await expect(page.getByRole('checkbox', { name: 'alpha', exact: true })).toBeChecked();
    });
});
