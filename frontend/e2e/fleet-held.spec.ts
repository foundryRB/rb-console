import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';

// A board the server could not refresh is HELD, not blanked (INT-FC-R144). The bug: one flaky
// org read made the server publish an empty fleet, so the whole floor vanished for a tick and
// the empty state told the operator to go fix a git token that was never the problem. The board
// now stands on the last good scan - and has to SAY it is standing on it, because a held board
// and a current one carry byte-identical projects.
//
// The second half is the forced rescan's ✓. Its guard against a blanking refresh tested
// `!poll.projects`, which an empty array passes, so the one outcome it was written to prevent
// flashed a success tick. A rescan that could not read the org is a failed rescan however many
// projects it managed to hand back.

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

const STALE = { since: '2026-08-27T09:42:03+00:00', why: 'the org could not be read: <urlopen error timed out>' };

type Fleet = { projects: typeof PROJECT[]; stale_since: string | null; stale_reason: string };

async function stubApi(page: Page, fleet: Fleet) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        if (path.startsWith('/chat/turns/')) return body({ status: 'done', ...fleet });
        switch (path) {
            case '/fleet':
                return body(fleet);
            case '/fleet/refresh':
                return body({ turn: 'stub-turn' });
            case '/maintenance/inbox':
                return body({ items: [], scanned: true });
            case '/studios':
                return body({ studios: [] });
            default:
                return body({});
        }
    });
    await page.setViewportSize({ width: 1280, height: 900 });
}

test.describe('a board the server could not refresh (INT-FC-R144)', () => {
    test('the held board keeps its projects and says it is held', async ({ page }) => {
        await stubApi(page, { projects: [PROJECT], stale_since: STALE.since, stale_reason: STALE.why });
        await page.goto('/');

        // THE regression: the floor is still there. It did not stop existing because one
        // GitHub read timed out.
        await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();
        // ...and the operator is told the rows may have moved on without them.
        await expect(page.getByText(/Board held since/)).toBeVisible();
        await expect(page.getByText(/last good scan/)).toBeVisible();
    });

    test('a current board says nothing about staleness', async ({ page }) => {
        await stubApi(page, { projects: [PROJECT], stale_since: null, stale_reason: '' });
        await page.goto('/');

        await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();
        await expect(page.getByText(/Board held since/)).toHaveCount(0);
    });

    test('an empty board that could not be scanned does not blame the git token', async ({ page }) => {
        await stubApi(page, { projects: [], stale_since: STALE.since, stale_reason: STALE.why });
        await page.goto('/');

        await expect(page.getByText('The floor could not be read')).toBeVisible();
        // The copy that sent operators to Settings to re-enter a working token.
        await expect(page.getByText(/Set the git token in/)).toHaveCount(0);
    });

    test('an empty board that WAS scanned still points at Settings', async ({ page }) => {
        // The other half: holding the last good board must not cost us the honest empty state.
        await stubApi(page, { projects: [], stale_since: null, stale_reason: '' });
        await page.goto('/');

        await expect(page.getByText('No projects yet')).toBeVisible();
        await expect(page.getByText(/Set the git token in/)).toBeVisible();
    });

    test('a rescan that could not read the org reports failure, not a ✓', async ({ page }) => {
        await stubApi(page, { projects: [PROJECT], stale_since: STALE.since, stale_reason: STALE.why });
        await page.goto('/');
        await expect(page.getByRole('link', { name: 'fsrandomizer', exact: true })).toBeVisible();

        await page.getByRole('button', { name: /refresh/i }).click();

        await expect(page.getByText(/Refresh failed/)).toBeVisible();
        await expect(page.getByText('Refreshed', { exact: true })).toHaveCount(0);
    });
});
