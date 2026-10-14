import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';
import { localEditorNetwork } from './editor-network';

// Deterministic fixtures for the stubbed /api layer. Only the shape the pages read is
// modelled; everything unlisted falls through to {} (the loaders degrade silently).
const FLEET = [
    {
        repo: 'example-org/acme-widget',
        name: 'acme-widget',
        is_delivery: true,
        delivery_status: 'awaiting-gate',
        delivery_phase: 'build+ship',
        onboarded: true,
        live: 'running',
        updated: null,
        estimatekit: true,
        protopane: true,
        hidden: false,
    },
    {
        repo: 'example-org/bar-svc',
        name: 'bar-svc',
        is_delivery: false,
        delivery_status: null,
        delivery_phase: null,
        onboarded: true,
        live: 'paused',
        updated: null,
        estimatekit: false,
        protopane: false,
        hidden: false,
    },
];

const AGENTS = [
    { name: 'my-claude', provider: 'claude', base_url: '', model: 'sonnet', models: ['sonnet', 'haiku'], configured: true },
];

const TREE = [
    { path: 'README.md', type: 'blob', size: 100 },
    { path: 'src/main.tsx', type: 'blob', size: 200 },
    { path: 'devops/Dockerfile', type: 'blob', size: 50 },
];

const phase = (name: string, current: boolean, signed: string | null, record: string | null) => ({
    name,
    question: `${name}?`,
    skill: '',
    studio: null,
    gate: name === 'learn' ? null : name,
    gate_signed_on: signed,
    record,
    record_present: record !== null,
    is_current: current,
    needs_review: false,
    artifact: null,
});

const OVERVIEW = {
    repo: 'example-org/acme-widget',
    exists: true,
    status: 'awaiting-gate',
    phase: 'build+ship',
    next_skill: null,
    next_command: null,
    blocked_gate: 'ship',
    gates: [
        { name: 'scope', signed_on: '2026-07-10' },
        { name: 'design', signed_on: '2026-07-11' },
        { name: 'plan', signed_on: '2026-07-11' },
        { name: 'ship', signed_on: null },
    ],
    records_present: ['scope.md', 'design.md', 'build.md'],
    config: { mode: 'interactive', provider: 'claude', base_url: '', model: 'sonnet', agent: 'my-claude', credentialed: true },
    phases: [
        phase('scope', false, '2026-07-10', 'scope.md'),
        phase('design', false, '2026-07-11', 'design.md'),
        phase('intent+plan', false, '2026-07-11', 'intent.md'),
        phase('build+ship', true, null, 'build.md'),
        phase('learn', false, null, null),
    ],
};

/** A repo live on the platform with no open line: the cockpit with no run-shape strip, at
 * production widths. The repo line under the name sets the name block's width, so the slug
 * carries an org name as long as a real one; a native select is as wide as its longest
 * option, so the model picker carries real model ids. At these widths the masthead overran
 * 1536px before #132's resizing, so this test fails if the resizing is undone. */
const LIVE_AGENTS = [
    {
        name: 'Studio Claude',
        provider: 'claude',
        base_url: '',
        model: 'claude-opus-5',
        models: ['claude-opus-5', 'claude-sonnet-5'],
        configured: true,
    },
];
const LIVE_OVERVIEW = {
    ...OVERVIEW,
    repo: 'Example-Department-of-Engineering/alexandria',
    exists: false,
    status: 'not-a-delivery',
    phase: null,
    blocked_gate: null,
    gates: [],
    records_present: [],
    phases: [],
    config: { ...OVERVIEW.config, model: 'claude-opus-5', agent: 'Studio Claude' },
};

/** Stub every /api call in-browser, so the real pages render with deterministic data and
 * no orchestrator is needed. Unlisted paths return {} - the store's loaders swallow it. */
async function stubApi(
    page: Page,
    overview: typeof OVERVIEW | typeof LIVE_OVERVIEW = OVERVIEW,
    agents: typeof AGENTS = AGENTS,
) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        switch (path) {
            case '/fleet':
                return body({ projects: FLEET });
            case '/studios':
                return body({ studios: [] });
            case '/maintenance/inbox':
                return body({ items: [], scanned: true });
            case '/deliveries/overview':
                return body(overview);
            case '/deliveries/state':
                return body(overview);
            case '/deliveries/config':
                return body(overview.config);
            case '/agents':
                return body({ agents });
            case '/runs':
                return body({ runs: [] });
            case '/deliveries/tree':
                return body({ tree: TREE });
            case '/deliveries/substance':
                return body({});
            case '/deliveries/file':
                return body({ path: '.delivery/build.md', content: '# build\n\nshipped.\n', size: 20 });
            default:
                return body({});
        }
    });
}

const overflowX = (page: Page) =>
    page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

const DESKTOP = { width: 1280, height: 900 };
const MOBILE = { width: 390, height: 844 };
const TABLET = { width: 834, height: 1112 };
// A 1920 x 1080 laptop on Windows' default 125% scaling.
const LAPTOP_125 = { width: 1536, height: 864 };

test.describe('masthead + fleet', () => {
    test.beforeEach(async ({ page }) => {
        await stubApi(page);
    });

    test('desktop: inline controls, table view, co-pilot open, no overflow', async ({ page }) => {
        await page.setViewportSize(DESKTOP);
        await page.goto('/');
        await expect(page.getByRole('table')).toBeVisible();
        const s = await page.evaluate(() => {
            const inline = document.querySelector('header [class~="flex-1"]');
            const controls = [...document.querySelectorAll('header button')].find((b) =>
                (b.textContent ?? '').trim().startsWith('Controls'),
            );
            return {
                inlineBar: inline ? getComputedStyle(inline).display : 'absent',
                controls: controls ? getComputedStyle(controls).display : 'absent',
                composer: !!document.querySelector('main textarea'),
            };
        });
        expect(s.inlineBar).toBe('flex'); // the dense bar is inline on desktop
        expect(s.controls).toBe('none'); // no disclosure button on desktop
        expect(s.composer).toBe(true); // co-pilot open by default on desktop
        expect(await overflowX(page)).toBe(0);
    });

    test('mobile: controls disclosure, tiles view, co-pilot collapsed, no overflow', async ({ page }) => {
        await page.setViewportSize(MOBILE);
        await page.goto('/');
        await expect(page.getByText('acme-widget').first()).toBeVisible(); // app mounted + fleet rendered
        await expect(page.getByRole('table')).toHaveCount(0); // tiles, not the wide table
        const before = await page.evaluate(() => {
            const inline = document.querySelector('header [class~="flex-1"]');
            const controls = [...document.querySelectorAll('header button')].find((b) =>
                (b.textContent ?? '').trim().startsWith('Controls'),
            );
            return {
                inlineBar: inline ? getComputedStyle(inline).display : 'absent',
                controls: controls ? getComputedStyle(controls).display : 'absent',
                composer: !!document.querySelector('main textarea'),
                disclosure: !!document.querySelector('header .basis-full'),
            };
        });
        expect(before.inlineBar).toBe('none'); // dense bar hidden below lg
        expect(before.controls).toBe('flex'); // disclosure button present
        expect(before.composer).toBe(false); // co-pilot collapsed by default on mobile
        expect(before.disclosure).toBe(false); // disclosure starts closed
        expect(await overflowX(page)).toBe(0);

        await page.getByRole('button', { name: 'Controls' }).click();
        const opened = await page.evaluate(() => {
            const d = document.querySelector('header .basis-full');
            return d ? getComputedStyle(d).display : 'absent';
        });
        expect(opened).toBe('flex'); // controls reveal, stacked
        expect(await overflowX(page)).toBe(0);
    });
});

test.describe('delivery cockpit split', () => {
    test.beforeEach(async ({ page }) => {
        await stubApi(page);
    });

    const probe = (page: Page) =>
        page.evaluate(() => {
            const grid = document.querySelector('main div[class*="lg:grid-cols-"]');
            const toggleBtn = [...document.querySelectorAll('main button')].find((b) =>
                ['Workspace', 'Console'].includes((b.textContent ?? '').trim()),
            );
            const toggle = toggleBtn?.parentElement ?? null;
            const wt = grid?.querySelector('div[class*="min-h-[420px]"]') ?? null;
            return {
                tracks: grid ? getComputedStyle(grid).gridTemplateColumns.trim().split(/\s+/).length : 0,
                cards: grid ? [...grid.children].map((c) => getComputedStyle(c).display) : [],
                paneToggle: toggle ? getComputedStyle(toggle).display : 'absent',
                worktreeDir: wt ? getComputedStyle(wt).flexDirection : 'absent',
            };
        });

    test('desktop: two columns side by side, worktree row, no pane tabs', async ({ page }) => {
        await page.setViewportSize(DESKTOP);
        await page.goto('/d?repo=example-org%2Facme-widget');
        await expect(page.getByRole('heading', { name: 'build+ship' })).toBeVisible();
        await page.getByRole('button', { name: 'Load phase content', exact: true }).click();
        const s = await probe(page);
        expect(s.tracks).toBe(2); // minmax(0,1fr) 400px
        expect(s.cards).toEqual(['flex', 'flex']); // both panes visible
        expect(s.paneToggle).toBe('none'); // no mobile tab bar
        expect(s.worktreeDir).toBe('row'); // tree beside viewer
        expect(await overflowX(page)).toBe(0);
    });

    test('the local worktree editor renders TypeScript and references selected lines with CDN blocked', async ({ page, baseURL }, testInfo) => {
        test.setTimeout(60_000);
        const network = await localEditorNetwork(page, baseURL!);
        await page.route('**/api/deliveries/file?*', (route) => route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({ path: 'src/main.tsx', content: 'export const shipped: boolean = true;\n', size: 38 }),
        }));
        await page.setViewportSize(DESKTOP);
        await page.goto('/d?repo=example-org%2Facme-widget');
        await page.getByRole('button', { name: 'Load phase content', exact: true }).click();
        await page.getByRole('button', { name: 'Load file tree', exact: true }).click();
        await page.getByRole('button', { name: 'main.tsx', exact: true }).click();
        const editor = page.locator('.monaco-editor');
        await expect(editor).toBeVisible({ timeout: 20_000 });
        await expect(editor.locator('.view-lines')).toContainText('shipped');
        await expect.poll(() => network.workers.some((url) => /ts\.worker/.test(url))).toBe(true);
        await expect.poll(() => network.responses.some(({ url, status }) => /ts\.worker/.test(url) && status === 200)).toBe(true);
        await editor.locator('.view-lines').click({ position: { x: 100, y: 5 } });
        await page.keyboard.press('ControlOrMeta+a');
        await page.getByRole('button', { name: 'selection → co-pilot' }).click();
        await expect(page.getByRole('button', { name: '⎘ src/main.tsx#L1-L2 ✕', exact: true })).toBeVisible();
        expect(network.external).toEqual([]);
        expect(network.errors).toEqual([]);
        expect(network.responses.every(({ status }) => status === 200)).toBe(true);
        const sanitizers = await network.checkSanitizer();
        await testInfo.attach('local-editor-network', { body: JSON.stringify({ ...network, sanitizers }, null, 2), contentType: 'application/json' });
        await testInfo.attach('local-worktree-editor', { body: await page.screenshot(), contentType: 'image/png' });
    });

    test('mobile: one column, tabs switch panes, worktree stacked, no overflow', async ({ page }) => {
        await page.setViewportSize(MOBILE);
        await page.goto('/d?repo=example-org%2Facme-widget');
        await expect(page.getByRole('heading', { name: 'build+ship' })).toBeVisible();
        await page.getByRole('button', { name: 'Load phase content', exact: true }).click();
        const s = await probe(page);
        expect(s.tracks).toBe(1); // single column
        expect(s.cards).toEqual(['flex', 'none']); // Workspace shown, Console hidden
        expect(s.paneToggle).toBe('flex'); // tab bar visible
        expect(s.worktreeDir).toBe('column'); // tree stacked above viewer
        expect(await overflowX(page)).toBe(0);

        await page.getByRole('button', { name: 'Console' }).click();
        const after = await probe(page);
        expect(after.cards).toEqual(['none', 'flex']); // Console shown, Workspace hidden
        expect(await overflowX(page)).toBe(0);
    });

    test('tablet portrait (834): single-column tabbed layout, no overflow', async ({ page }) => {
        await page.setViewportSize(TABLET);
        await page.goto('/d?repo=example-org%2Facme-widget');
        await expect(page.getByRole('heading', { name: 'build+ship' })).toBeVisible();
        await page.getByRole('button', { name: 'Load phase content', exact: true }).click();
        const s = await probe(page);
        expect(s.tracks).toBe(1); // tablet portrait is below lg: stacked, not starved
        expect(s.paneToggle).toBe('flex');
        expect(await overflowX(page)).toBe(0);
    });
});

// The masthead's page controls are hoisted into it so the cockpit spends no second header row
// (Cockpit.tsx), but its bar is flex-wrap: an overgrown bar wraps rather than overflowing, so
// the overflow checks above stay green on a two-row masthead. That is how it grew past the
// width of a 1920 x 1080 laptop on 125% scaling unnoticed, one control at a time (issue #132).
test.describe('masthead holds one row on a 125%-scaled 1080p laptop', () => {
    /** Every visible masthead control shares one horizontal band: the lowest top sits above
     * the highest bottom. A control wrapped onto a second row starts below the first row's
     * bottoms, so it fails this. */
    const mastheadRow = (page: Page) =>
        page.evaluate(() => {
            const controls = 'header button, header select, header input, header nav a';
            const boxes = [...document.querySelectorAll(controls)]
                .map((el) => el.getBoundingClientRect())
                .filter((r) => r.width > 0 && r.height > 0);
            const lowestTop = Math.max(...boxes.map((r) => r.top));
            const highestBottom = Math.min(...boxes.map((r) => r.bottom));
            return { controls: boxes.length, oneRow: lowestTop < highestBottom };
        });

    test('open delivery line: one row, the run shape beside Drive', async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize(LAPTOP_125);
        await page.goto('/d?repo=example-org%2Facme-widget');
        await expect(page.getByRole('heading', { name: 'build+ship' })).toBeVisible();
        await page.getByRole('button', { name: 'Load phase content', exact: true }).click();
        await expect(page.locator('header select').first()).toBeVisible();
        const s = await mastheadRow(page);
        expect(s.controls).toBeGreaterThan(5); // the toggle, the pickers, the stepper, Settings
        expect(s.oneRow).toBe(true);
        // The run shape left the masthead for the line card, beside the act it paces.
        const oneShot = { name: 'One-shot' };
        await expect(page.locator('header').getByRole('button', oneShot)).toHaveCount(0);
        await expect(page.locator('main').getByRole('button', oneShot)).toBeVisible();
        expect(await overflowX(page)).toBe(0);
    });

    test('live, no open line: one row', async ({ page }) => {
        await stubApi(page, LIVE_OVERVIEW, LIVE_AGENTS);
        await page.setViewportSize(LAPTOP_125);
        await page.goto(`/d?repo=${encodeURIComponent(LIVE_OVERVIEW.repo)}`);
        await expect(page.locator('header select').first()).toBeVisible();
        const s = await mastheadRow(page);
        expect(s.controls).toBeGreaterThan(5);
        expect(s.oneRow).toBe(true);
        expect(await overflowX(page)).toBe(0);
    });
});
