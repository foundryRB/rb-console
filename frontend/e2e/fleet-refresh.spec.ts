import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';

// The Fleet board is served from the server's warm cache, which only turns over every configured
// interval; an operator returning to the fleet after a burst of work should not have to wait out
// the cycle. The masthead's refresh control asks the server for a rescan NOW (POST /fleet/refresh,
// INT-FC-R107) - re-reading the warm cache would answer identical data until the tick lands - then
// re-pulls the inbox and the studios, which that rescan just recomputed, and reports its outcome.
// Issue #27. The rescan is dozens of GitHub reads, long enough to outlast the proxy chain the same
// way an ungrounded chat turn once did (INT-FC-R55), so the POST answers a turn id at once and the
// control polls the shared turn endpoint for the fleet the rescan produced (issue #36).

const PROJECT = {
    repo: 'example-org/fsrandomizer',
    name: 'fsrandomizer',
    is_delivery: false,
    delivery_status: null,
    delivery_phase: null,
    onboarded: true,
    live: 'running',
    updated: 't',
    estimatekit: false,
    protopane: false,
    hidden: false,
    role: 'output',
    activity: null,
};

type Calls = { refresh: number; turn: number; fleet: number; inbox: number; studios: number };

/** How the turn poll answers. 'done' is the ordinary rescan that lands inside the first poll;
 * 'pending' never lands, standing in for a rescan still grinding through its GitHub reads when
 * the SPA's deadline passes (issue #39). Mutable through the returned handle, so a test can
 * land the rescan AFTER the SPA's give-up and assert the board catches up (issue #46). */
type TurnMode = 'done' | 'pending';
type Stub = { calls: Calls; turn: { mode: TurnMode } };

// Stub the /api layer and count how many times each endpoint is hit, so a click on the refresh
// control can be asserted to trigger the rescan action (not a cache re-read) plus the two re-pulls.
// /fleet/refresh answers a turn id at once (INT-FC-R107); the poll lands 'done' on the first hit,
// same as a rescan the backend finishes well inside the SPA's first poll interval.
async function stubApi(page: Page, turnMode: TurnMode = 'done'): Promise<Stub> {
    const calls: Calls = { refresh: 0, turn: 0, fleet: 0, inbox: 0, studios: 0 };
    const turn = { mode: turnMode };
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        if (path.startsWith('/chat/turns/')) {
            calls.turn += 1;
            return turn.mode === 'pending'
                ? body({ status: 'pending' })
                : body({ status: 'done', projects: [PROJECT] });
        }
        switch (path) {
            case '/fleet/refresh':
                calls.refresh += 1;
                return body({ turn: 'stub-turn' });
            case '/fleet':
                calls.fleet += 1;
                return body({ projects: [PROJECT] });
            case '/maintenance/inbox':
                calls.inbox += 1;
                return body({ items: [], scanned: true });
            case '/studios':
                calls.studios += 1;
                return body({ studios: [] });
            default:
                return body({});
        }
    });
    return { calls, turn };
}

/** Wait until the pull counts stop moving, so a baseline is taken from a finished mount rather than
 * from the middle of one. */
async function settle(calls: Calls) {
    let prev = '';
    await expect
        .poll(
            () => {
                const now = JSON.stringify(calls);
                const stable = now !== '' && now === prev;
                prev = now;
                return stable;
            },
            { intervals: [100, 100, 100, 100, 100, 200, 200] },
        )
        .toBe(true);
}

test.describe('the Fleet manual refresh (issue #27)', () => {
    test('the refresh control re-pulls the fleet, the inbox, and the studios on demand', async ({ page }) => {
        const { calls } = await stubApi(page);
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/');
        await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();

        // The mount pulled each cache-backed endpoint. Take the baseline rather than asserting an
        // exact count: this suite drives the Vite dev server, where StrictMode double-invokes mount
        // effects, so mount legitimately pulls each endpoint twice in dev and once in a production
        // build. The claim under test is what the CLICK adds, which that difference must not decide.
        await settle(calls);
        const base = { ...calls };
        expect(base.fleet).toBeGreaterThan(0);
        expect(base.inbox).toBeGreaterThan(0);
        expect(base.studios).toBeGreaterThan(0);

        const refresh = page.getByRole('button', { name: 'Refresh the fleet now' });
        await expect(refresh).toBeVisible();
        await refresh.click();

        // The click triggered exactly one rescan action (started off the wire, INT-FC-R107)
        // and one poll of the turn it started - not a warm-cache GET of the fleet - plus one
        // re-pull each of the inbox and the studios the rescan recomputed. One click is one
        // rescan rather than a storm.
        await expect.poll(() => ({ ...calls })).toEqual({
            refresh: base.refresh + 1,
            turn: base.turn + 1,
            fleet: base.fleet,
            inbox: base.inbox + 1,
            studios: base.studios + 1,
        });

        // And the control reports the outcome: the flash, then the landed rescan's time.
        await expect(page.getByText(/^(Refreshed|Updated )/)).toBeVisible();
    });

    // The rescan runs off the wire under no server-side bound (hundreds of sequential GitHub
    // reads), while the SPA's poll carries a give-up deadline inherited from the chat turn,
    // where a 180s model bound justifies it. Crossing that deadline says the SPA stopped
    // waiting - the rescan is still running and its fleet still lands in the warm cache - so
    // reporting 'Refresh failed' told the operator the inverse of the truth (issue #39,
    // INT-FC-R107). The deadline is shortened here so the give-up needs no 200s test.
    test('a rescan that outlives the poll reads as still running, not as a failure', async ({ page }) => {
        await page.addInitScript(() => {
            (globalThis as { __turnDeadlineMs?: number }).__turnDeadlineMs = 1_000;
        });
        const { calls, turn } = await stubApi(page, 'pending');
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/');
        await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();
        await settle(calls);
        const base = { ...calls };

        await page.getByRole('button', { name: 'Refresh the fleet now' }).click();

        // The honest degrade: still running, never 'Refresh failed'.
        await expect(page.getByText('Still refreshing - the board will catch up')).toBeVisible();
        await expect(page.getByText(/^Refresh failed/)).toHaveCount(0);

        // And it re-read the warm cache on the way out, so a rescan that landed between the
        // give-up and now reaches the board without a page reload.
        expect(calls.fleet).toBeGreaterThan(base.fleet);

        // The give-up is not an abandonment: the control keeps watching the turn, so when
        // the rescan finally lands server-side the board catches up on its own - the note
        // resolves to the landed rescan's time with no reload and no second click
        // (issue #46). One click, one rescan action, however long it ran.
        turn.mode = 'done';
        await expect(page.getByText(/^Updated /)).toBeVisible({ timeout: 10_000 });
        await expect(page.getByText('Still refreshing - the board will catch up')).toHaveCount(0);
        expect(calls.refresh).toBe(base.refresh + 1);
    });
});


test('a completed refresh retains the source observation freshness and partial coverage', async ({ page }) => {
    await stubApi(page);
    await page.route('**/api/chat/turns/stub-turn', async (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        status: 'done', projects: [], freshness: { state: 'stale', observed_at: '2026-10-05T12:00:00Z', last_attempt_at: '2026-10-05T12:01:00Z', reason_code: 'partial_collection', coverage: { complete: false, observed: 0, total: 2 } },
    }) }));
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Refresh the fleet now' }).click();
    // An empty board standing on partial coverage reads as pending, never as an empty org.
    await expect(page.getByText('Observation pending')).toBeVisible();
    await expect(page.getByText('The scheduled observation is still incomplete.')).toBeVisible();
    await expect(page.getByText('No projects yet')).toHaveCount(0);
});

test('a board read that fails while rows are on screen says the board is the last one', async ({ page }) => {
    await stubApi(page);
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();
    await page.route('**/api/fleet', async (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
    // Leave the board and come back inside the SPA: the store keeps its rows and the remount reads again.
    await page.evaluate(() => {
        history.pushState({}, '', '/studios');
        dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect(page.getByRole('heading', { name: 'Studios' })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();
    const lastBoard = page.getByRole('status').filter({ hasText: 'Showing the last board' });
    await expect(lastBoard).toBeVisible();
    await expect(lastBoard).toHaveClass(/text-destructive/);
    // A rescan whose board lands replaces the failed read: the line confirms it.
    await page.getByRole('button', { name: 'Refresh the fleet now' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Refreshed' })).toBeVisible();
    await expect(lastBoard).toHaveCount(0);
});

test('a rescan still running reads neutral even when the cache re-read fails', async ({ page }) => {
    await page.addInitScript(() => {
        (globalThis as { __turnDeadlineMs?: number }).__turnDeadlineMs = 1_000;
    });
    await stubApi(page, 'pending');
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();
    await page.route('**/api/fleet', async (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
    await page.getByRole('button', { name: 'Refresh the fleet now' }).click();
    const pending = page.getByRole('status').filter({ hasText: 'Still refreshing - the board will catch up' });
    await expect(pending).toBeVisible();
    await expect(pending).not.toHaveClass(/text-destructive/);
});
