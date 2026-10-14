import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';

// The Fleet board's project search (issue #55): a search box above the list filters the board by
// name as the operator types, matching the app name OR its owner/name repo slug (the two
// identifiers a row shows). The term rides the URL (?q=) so a filtered view is a shareable link,
// and a match that lives only among the collapsed Foundry-core apps is revealed while searching.

const project = (over: Partial<Record<string, unknown>> & { repo: string; name: string }) => ({
    is_delivery: false,
    delivery_status: null,
    delivery_phase: null,
    onboarded: true,
    live: 'running',
    updated: 't',
    estimatekit: false,
    protopane: false,
    hidden: false,
    role: null,
    activity: null,
    ...over,
});

// Two tenant apps, one whose display name differs from its repo slug tail (so a repo-only match is
// exercised), a bare repo, and two Foundry-core (parts) apps that collapse by default.
const PROJECTS = [
    project({ repo: 'example-org/tectonic-globe', name: 'tectonic-globe', role: 'output' }),
    project({ repo: 'example-org/fsrandomizer', name: 'fsrandomizer', role: 'output' }),
    project({ repo: 'example-org/acme-widget', name: 'widget', role: 'output' }),
    project({ repo: 'example-org/some-lib', name: 'some-lib', onboarded: false, live: null, role: null }),
    project({ repo: 'example-org/foundry-console', name: 'foundry-console', role: 'parts' }),
    project({ repo: 'example-org/platform-studio', name: 'platform-studio', role: 'parts' }),
];

async function stubApi(page: Page) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        switch (path) {
            case '/fleet':
                return body({ projects: PROJECTS });
            case '/maintenance/inbox':
                return body({ items: [], scanned: true });
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({ agents: [] });
            case '/runs':
                return body({ runs: [] });
            default:
                return body({});
        }
    });
}

const nameLink = (page: Page, name: string) => page.getByRole('link', { name, exact: true });
const searchBox = (page: Page) => page.getByRole('textbox', { name: 'Search projects by name' });

test.describe('the Fleet project search (#55)', () => {
    test.beforeEach(async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/');
        await expect(nameLink(page, 'tectonic-globe')).toBeVisible();
    });

    test('typing narrows the board to name matches, and clearing restores it', async ({ page }) => {
        await searchBox(page).fill('tectonic');
        await expect(nameLink(page, 'tectonic-globe')).toBeVisible();
        await expect(nameLink(page, 'fsrandomizer')).toHaveCount(0);
        await expect(nameLink(page, 'widget')).toHaveCount(0);

        // The clear (×) button empties the box and brings the whole board back.
        await page.getByRole('button', { name: 'Clear search' }).click();
        await expect(searchBox(page)).toHaveValue('');
        await expect(nameLink(page, 'fsrandomizer')).toBeVisible();
        await expect(nameLink(page, 'widget')).toBeVisible();
    });

    test('the search matches the owner/name repo slug, not only the display name', async ({ page }) => {
        // 'acme' is in the repo (example-org/acme-widget) but not in the display name ('widget').
        await searchBox(page).fill('acme');
        await expect(nameLink(page, 'widget')).toBeVisible();
        await expect(nameLink(page, 'tectonic-globe')).toHaveCount(0);
    });

    test('the term persists in the URL, and a ?q= link opens pre-filtered', async ({ page }) => {
        await searchBox(page).fill('tectonic');
        await expect(page).toHaveURL(/[?&]q=tectonic/);

        // A fresh load of the shared link starts filtered, with the box carrying the term.
        await page.goto('/?q=fsrandom');
        await expect(searchBox(page)).toHaveValue('fsrandom');
        await expect(nameLink(page, 'fsrandomizer')).toBeVisible();
        await expect(nameLink(page, 'tectonic-globe')).toHaveCount(0);
    });

    test('a search reveals a match hiding in the collapsed Foundry-core group', async ({ page }) => {
        // foundry-console is a 'parts' app, hidden under the collapsed Foundry-core header by default.
        await expect(nameLink(page, 'foundry-console')).toHaveCount(0);
        await searchBox(page).fill('foundry');
        // The search surfaces it without an explicit expand, and drops the non-matching tenant apps.
        await expect(nameLink(page, 'foundry-console')).toBeVisible();
        await expect(nameLink(page, 'platform-studio')).toHaveCount(0);
        await expect(nameLink(page, 'tectonic-globe')).toHaveCount(0);
    });

    test('a no-match search names the term and offers a clear back to the full board', async ({ page }) => {
        await searchBox(page).fill('nothingmatchesthis');
        await expect(page.getByText(/No projects match .*nothingmatchesthis/)).toBeVisible();
        await page.getByRole('button', { name: 'Clear', exact: true }).click();
        await expect(nameLink(page, 'tectonic-globe')).toBeVisible();
    });
});
