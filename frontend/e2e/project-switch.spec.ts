import { contractFixture } from './contract-fixture';
import { expect, test, type Page } from '@playwright/test';

// Opening another project left the previous one's data on screen. The store's per-project
// slots - overview/current, substance/record, tree/openFile, references, the run graph and
// its logs - are single, and only the page's LOCAL state was reset on a repo change, so the
// panes kept whatever was last loaded: the old line, the old worktree, the old repo link,
// all under the new project's name. A failed read never replaced them at all, and a slow one
// for the project you LEFT could land on the project you opened. The co-pilot was the sharp
// end - its references (the ticked worktree paths) rode along, so a turn about the new
// project was grounded on the previous project's files.
//
// The store now stamps the project it describes (viewedRepo) and drops any response that
// lands after the operator moved on; the page reads its panes only while that stamp matches
// the repo in the URL. Issue #60.
//
// Three things this suite learned the hard way, each of which made an earlier version of it
// pass against the UNFIXED code:
//  - Switching must go through the ROUTER (a fleet row click), never page.goto: a fresh load
//    rebuilds the store from scratch and the bug cannot appear at all.
//  - The new project's reads must be held OPEN. Against instant stubs the replacement data
//    lands before any assertion runs, so the stale window - the seconds a real GitHub read
//    takes, which is the whole complaint - never exists to observe.
//  - Judge only AFTER a positive marker says the new cockpit has rendered. A bare
//    "the old data is absent" passes on the blink between two pages, when everything is.
//
// The witness throughout is the repo the cockpit LINKS to (current.repo), not the name in
// the masthead: that name is derived from the URL and reads correctly even when every pane
// below it belongs to the project before.

const phases = (current: string) =>
    ['scope', 'design', 'intent+plan', 'build+ship', 'learn'].map((name, i) => ({
        name,
        question: `Q${i}`,
        skill: 'some-skill',
        studio: null,
        gate: name === 'learn' ? null : ['proposal', 'design', 'plan', 'delivery'][i],
        gate_signed_on: null,
        record: name === 'learn' ? null : `${name}.md`,
        record_present: name === current,
        is_current: name === current,
        needs_review: false,
        artifact: null,
    }));

const overview = (repo: string, current: string) => ({
    repo,
    exists: true,
    status: 'in-progress',
    phase: current,
    next_skill: null,
    next_command: null,
    blocked_gate: null,
    gates: [],
    records_present: [`${current}.md`],
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
    phases: phases(current),
});

// Two projects with nothing in common: a different repo, a different record body, a
// different worktree file. Both sit on build+ship, the phase whose pane carries the worktree
// and its co-pilot reference ticks.
const ALPHA = {
    repo: 'example-org/alpha-widget',
    name: 'alpha-widget',
    record: 'ALPHA RECORD BODY',
    file: 'alpha-only.ts',
};
const BRAVO = {
    repo: 'example-org/bravo-widget',
    name: 'bravo-widget',
    record: 'BRAVO RECORD BODY',
    file: 'bravo-only.ts',
};
const projects = [ALPHA, BRAVO];
const forRepo = (repo: string | null) => projects.find((p) => p.repo === repo) ?? ALPHA;

const fleetItem = (p: typeof ALPHA) => ({
    repo: p.repo,
    name: p.name,
    is_delivery: true,
    delivery_status: 'in-progress',
    delivery_phase: 'build+ship',
    onboarded: false,
    live: null,
    updated: '2026-08-10T18:57:00Z',
    estimatekit: false,
    protopane: false,
    hidden: false,
    role: null,
    activity: null,
});

/** A read the test opens and closes by hand, so the window between "you switched" and "the
 *  new project's data arrived" is wide enough to look at - the window a real GitHub-backed
 *  read leaves open for seconds, and the one the whole report is about. */
class Gate {
    private open!: () => void;
    readonly held = new Promise<void>((r) => {
        this.open = r;
    });
    release() {
        this.open();
    }
}

interface StubOptions {
    /** Repos whose overview read fails, to prove a failed load shows nothing rather than the last project. */
    overviewFails?: string[];
    /** Repos whose overview the observation could not read from its source. */
    sourceUnreachable?: string[];
    /** Repo whose project reads hang until the gate is released. */
    hold?: { repo: string; gate: Gate };
    /** Every project-scoped read as `path::repo`, recorded when ISSUED and again when SERVED.
     *  A held read sits between the two, which is exactly the interval a test needs to aim at. */
    requested?: string[];
    served?: string[];
    /** Collects every co-pilot turn's request body. */
    turns?: unknown[];
}

async function stubApi(page: Page, opts: StubOptions = {}) {
    await page.route('**/api/**', async (route) => {
        const url = new URL(route.request().url());
        const path = url.pathname.replace(/^\/api/, '');
        const repo = url.searchParams.get('repo');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        const p = forRepo(repo);
        if (repo) opts.requested?.push(`${path}::${repo}`);
        // Every per-project read waits on the gate, so holding one holds the whole cockpit.
        if (opts.hold && repo === opts.hold.repo) await opts.hold.gate.held;
        if (repo) opts.served?.push(`${path}::${repo}`);
        switch (path) {
            case '/deliveries/overview':
            case '/deliveries/state':
                if (opts.overviewFails?.includes(repo ?? '')) {
                    return route.fulfill({
                        status: 500,
                        contentType: 'application/json',
                        body: JSON.stringify({ detail: 'overview read failed' }),
                    });
                }
                return body({
                    ...overview(p.repo, 'build+ship'),
                    ...(opts.sourceUnreachable?.includes(repo ?? '') && {
                        freshness: {
                            state: 'unavailable',
                            observed_at: null,
                            last_attempt_at: '2026-10-10T09:00:00Z',
                            reason_code: 'source_unavailable',
                            coverage: { complete: false, observed: 0, total: 4 },
                        },
                    }),
                });
            case '/deliveries/config':
                return body(overview(p.repo, 'build+ship').config);
            case '/deliveries/substance':
                return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
            case '/deliveries/file':
                return body({ path: url.searchParams.get('path'), content: p.record });
            case '/deliveries/tree':
                return body({ tree: [{ path: p.file, type: 'blob' }] });
            case '/deliveries/chat':
                opts.turns?.push(route.request().postDataJSON());
                return body({ turn: 't1' });
            case '/chat/turns/t1':
                return body({ status: 'done', configured: true, model: 'claude-opus-5', reply: 'ok' });
            case '/runs':
                return body({ runs: [] });
            case '/fleet':
                return body({ projects: projects.map(fleetItem) });
            // The fleet page's own strips. Each reads a list off its response, so an empty
            // object is not a safe default - it throws and the page renders nothing at all.
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({ agents: [] });
            case '/deliveries':
                return body({ deliveries: [] });
            case '/maintenance/inbox':
                return body({ items: [] });
            default:
                return body({});
        }
    });
}

/** Whose data the cockpit actually holds: the repo it links to, straight off the loaded
 *  overview. Distinct from the masthead name, which the URL alone supplies. */
const linkedRepo = (page: Page, project: typeof ALPHA) => page.getByText(project.repo, { exact: false });
/** The cockpit with no project loaded yet - the honest state during a switch. */
const loading = (page: Page) => page.getByText('Loading delivery…');
/** The worktree's per-file "feed this to the co-pilot" ticks. */
const refTicks = (page: Page) => page.getByTitle('reference this file in the co-pilot chat');
const ask = (page: Page) => page.getByPlaceholder('Ask the co-pilot…').first();
const fleetRow = (page: Page, project: typeof ALPHA) =>
    page.getByRole('row').filter({ hasText: project.repo }).first();

/** One full load, then every move is client-side. */
async function startAtFleet(page: Page) {
    await page.goto('/');
    await expect(fleetRow(page, ALPHA)).toBeVisible();
}

/** Back to the fleet without reloading: the masthead logo is a router Link. */
async function backToFleet(page: Page) {
    await page.getByTitle('Back to the fleet').click();
    await expect(fleetRow(page, ALPHA)).toBeVisible();
}

/** Open a project from the fleet, the way an operator does - a router navigation, no reload,
 *  so the store carries whatever the last project left in it. */
async function openFromFleet(page: Page, project: typeof ALPHA) {
    await fleetRow(page, project).click();
}

/** Open alpha, wait for its cockpit to be fully its own, then go back to the fleet. */
async function loadThenLeaveAlpha(page: Page) {
    await openFromFleet(page, ALPHA);
    await page.getByRole("button", { name: "Load phase content", exact: true }).click();
        await page.getByRole("button", { name: "Load file tree", exact: true }).click();
    await expect(page.getByText(ALPHA.file)).toBeVisible();
    await expect(linkedRepo(page, ALPHA).first()).toBeVisible();
    await backToFleet(page);
}

test.describe('opening another project retires the one before it (issue #60)', () => {
    test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 900 });
    });

    test('while the new project loads, the cockpit shows nothing of the previous one', async ({ page }) => {
        const gate = new Gate();
        await stubApi(page, { hold: { repo: BRAVO.repo, gate } });
        await startAtFleet(page);
        await loadThenLeaveAlpha(page);

        await openFromFleet(page, BRAVO);
        // Bravo's reads are still in flight. THIS is the window the report is about, and the
        // cockpit's only honest answer for it is that it is loading - not alpha's line, its
        // worktree and its repo link sitting under bravo's name.
        await expect(loading(page)).toBeVisible();
        await expect(linkedRepo(page, ALPHA)).toHaveCount(0);
        await expect(page.getByText(ALPHA.file)).toHaveCount(0);

        gate.release();
        await page.getByRole("button", { name: "Load phase content", exact: true }).click();
        await page.getByRole("button", { name: "Load file tree", exact: true }).click();
        await expect(page.getByText(BRAVO.file)).toBeVisible();
        await expect(linkedRepo(page, BRAVO).first()).toBeVisible();
    });

    test('a failed overview read shows the failure, not the previous project’s line', async ({ page }) => {
        await stubApi(page, { overviewFails: [BRAVO.repo] });
        await startAtFleet(page);
        await loadThenLeaveAlpha(page);

        await openFromFleet(page, BRAVO);
        // The read failed, so bravo has no line to show. The old code only ever wrote on
        // success, so alpha's stayed rendered under bravo's URL - indefinitely, not just
        // for the length of a load.
        await expect(page.getByText('overview read failed')).toBeVisible();
        await expect(linkedRepo(page, ALPHA)).toHaveCount(0);
        await expect(page.getByText(ALPHA.file)).toHaveCount(0);
    });

    test('a source the observation could not read says so; a good read says nothing', async ({ page }) => {
        await stubApi(page, { sourceUnreachable: [BRAVO.repo] });
        await startAtFleet(page);
        await openFromFleet(page, ALPHA);
        await expect(linkedRepo(page, ALPHA).first()).toBeVisible();
        await expect(page.getByText(/source unreachable/)).toHaveCount(0);
        await backToFleet(page);
        await openFromFleet(page, BRAVO);
        await expect(page.getByText('Read unavailable - source unreachable')).toBeVisible();
    });

    test('a slow read for the project you left never lands on the one you opened', async ({ page }) => {
        const gate = new Gate();
        const requested: string[] = [];
        const served: string[] = [];
        await stubApi(page, { hold: { repo: ALPHA.repo, gate }, requested, served });
        await startAtFleet(page);
        const alphaOverview = `/deliveries/overview::${ALPHA.repo}`;

        // Open alpha, leave before its reads land, open bravo, then let alpha's land. Wait
        // for the read to have been ISSUED first: leaving faster than the cockpit's own
        // effect means there is no in-flight response to race, and the test proves nothing.
        await openFromFleet(page, ALPHA);
        await expect.poll(() => requested.includes(alphaOverview)).toBe(true);
        await backToFleet(page);
        await openFromFleet(page, BRAVO);
        await expect(linkedRepo(page, BRAVO).first()).toBeVisible();
        gate.release();

        // Wait for alpha's overview to actually be served before judging: the point is that
        // a response for a project no longer open is DROPPED, not merely late.
        await expect.poll(() => served.includes(alphaOverview)).toBe(true);
        await expect(linkedRepo(page, ALPHA)).toHaveCount(0);
        await expect(linkedRepo(page, BRAVO).first()).toBeVisible();
    });

    test('a co-pilot turn carries no references from the project before it', async ({ page }) => {
        const turns: unknown[] = [];
        await stubApi(page, { turns });
        await startAtFleet(page);
        await openFromFleet(page, ALPHA);

        await page.getByRole("button", { name: "Load phase content", exact: true }).click();
        await page.getByRole("button", { name: "Load file tree", exact: true }).click();
        // Tick alpha's file as grounding for its co-pilot.
        await refTicks(page).first().check();
        await expect(refTicks(page).first()).toBeChecked();

        await backToFleet(page);
        await openFromFleet(page, BRAVO);
        await page.getByRole("button", { name: "Load phase content", exact: true }).click();
        await page.getByRole("button", { name: "Load file tree", exact: true }).click();
        await expect(page.getByText(BRAVO.file)).toBeVisible();
        // The tick is clear on the new project - the grounding was alpha's, not a
        // console-wide preference.
        await expect(refTicks(page).first()).not.toBeChecked();

        await ask(page).fill('what is this project?');
        await ask(page).press('Enter');
        await expect.poll(() => turns.length).toBeGreaterThan(0);

        const sent = turns[0] as { target: string; references: string[] };
        expect(sent.target).toBe(BRAVO.repo);
        // The whole point: bravo's turn must not be grounded on alpha's files.
        expect(sent.references ?? []).not.toContain(ALPHA.file);
    });
});
