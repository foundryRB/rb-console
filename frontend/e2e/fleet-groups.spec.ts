import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';

// The Fleet board sets the apps that MAKE UP the Foundry (manifest role 'parts') apart from the
// apps it BUILDS AND RUNS ('output', plus bare repos and in-flight deliveries that join no manifest
// app). The distinction is a grouping, not a second status colour: the parts apps gather under one
// labelled, collapsible "Foundry core" header, collapsed by default, so the small, fixed platform
// set reads as the substrate under the tenant fleet rather than colouring the board. INT-FC-R101.
//
// Two rows join that group without being apps at all: the platform repo and the playbook, role
// 'core'. foundry.yaml declares them beside the parts and output lists because neither can hold a
// teams/ folder, so neither can ever be onboarded - and left ungrouped they read as ordinary
// tenant repos. They sort to the TOP of the group and carry a neutral 'core' badge, so their
// empty Live cells read as "nothing to deploy, by nature". INT-FC-R147.

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
    // The app's fleet name and host, distinct from the repository's name. Defaulted to
    // empty here so a row reads as a bare repo unless a case declares one; the cases that
    // matter set app_name to something that is NOT the repo name, because a fixture set
    // where the two always coincide is what let this divergence go unnoticed.
    app_name: '',
    host: '',
    ...over,
});

// Two parts (the Foundry itself), two output (its deliveries), one bare repo (no manifest role),
// and the two core repos the Foundry is built out of (never onboarded, nothing to deploy).
const PROJECTS = [
    project({
        repo: 'example-org/foundry-platform',
        name: 'foundry-platform',
        onboarded: false,
        live: null,
        role: 'core',
    }),
    project({ repo: 'example-org/playbook', name: 'playbook', onboarded: false, live: null, role: 'core' }),
    project({ repo: 'example-org/foundry-console', name: 'foundry-console', role: 'parts' }),
    project({ repo: 'example-org/platform-studio', name: 'platform-studio', role: 'parts' }),
    project({ repo: 'example-org/fsrandomizer', name: 'fsrandomizer', role: 'output' }),
    project({ repo: 'example-org/tectonic-globe', name: 'tectonic-globe', role: 'output' }),
    project({ repo: 'example-org/some-lib', name: 'some-lib', onboarded: false, live: null, role: null }),
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
const coreToggle = (page: Page) => page.getByRole('button', { name: /Foundry core/ });

test.describe('the Fleet platform-vs-tenant grouping (desktop table)', () => {
    test.beforeEach(async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/');
        await expect(nameLink(page, 'fsrandomizer')).toBeVisible();
    });

    test('the tenant apps are the main body; the parts apps hide under a labelled, counted header', async ({ page }) => {
        // 'output' and bare repos are the default fleet, always shown.
        await expect(nameLink(page, 'fsrandomizer')).toBeVisible();
        await expect(nameLink(page, 'tectonic-globe')).toBeVisible();
        await expect(nameLink(page, 'some-lib')).toBeVisible();
        // The two 'parts' apps are gathered under one header carrying their count...
        const toggle = coreToggle(page);
        await expect(toggle).toBeVisible();
        await expect(toggle.getByText('4', { exact: true })).toBeVisible();
        // ...and collapsed by default, so the platform set does not clutter the tenant board.
        await expect(nameLink(page, 'foundry-console')).toHaveCount(0);
        await expect(nameLink(page, 'platform-studio')).toHaveCount(0);
        // The core repos ride the same collapse - they are part of the Foundry, not the fleet.
        await expect(nameLink(page, 'foundry-platform')).toHaveCount(0);
        await expect(nameLink(page, 'playbook')).toHaveCount(0);
    });

    test('the platform and the playbook head the group, badged core', async ({ page }) => {
        await coreToggle(page).click();
        // Both are visible, and each carries the neutral 'core' badge that explains an empty
        // Live cell as "never deployed, by nature" rather than an app that failed to come up.
        for (const name of ['foundry-platform', 'playbook']) {
            const row = page.locator('tbody tr').filter({ has: nameLink(page, name) });
            await expect(row).toHaveCount(1);
            await expect(row.getByText('core', { exact: true })).toBeVisible();
        }
        // They sort ABOVE the parts apps: the group's own substrate, ahead of the column sort.
        const platformY = (await nameLink(page, 'foundry-platform').boundingBox())!.y;
        const playbookY = (await nameLink(page, 'playbook').boundingBox())!.y;
        const partsY = (await nameLink(page, 'foundry-console').boundingBox())!.y;
        expect(platformY).toBeLessThan(partsY);
        expect(playbookY).toBeLessThan(partsY);
        // ...and still below the tenant fleet, which keeps the board's top.
        const tenantY = (await nameLink(page, 'fsrandomizer').boundingBox())!.y;
        expect(platformY).toBeGreaterThan(tenantY);
    });

    test('expanding the header reveals the parts apps below it, and collapsing hides them again', async ({ page }) => {
        await coreToggle(page).click();
        await expect(nameLink(page, 'foundry-console')).toBeVisible();
        await expect(nameLink(page, 'platform-studio')).toBeVisible();
        // The revealed parts apps sit BELOW the tenant fleet (the substrate under the deliveries).
        const tenantY = (await nameLink(page, 'fsrandomizer').boundingBox())!.y;
        const coreY = (await nameLink(page, 'foundry-console').boundingBox())!.y;
        expect(coreY).toBeGreaterThan(tenantY);

        await coreToggle(page).click();
        await expect(nameLink(page, 'foundry-console')).toHaveCount(0);
    });

    test('the grouping adds no new status colour: only a paused app is tinted', async ({ page }) => {
        // With every app running, no row carries the amber paused wash - the group is a divider and
        // a disclosure, not a colour, so paused stays the board's one status hue.
        const painted = await page
            .locator('tbody tr')
            .evaluateAll((rows) => rows.filter((r) => /amber/.test(r.className)).length);
        expect(painted).toBe(0);
    });
});

test.describe('the Fleet grouping on mobile (tiles)', () => {
    test('the parts apps gather under the same collapsible band in the tile view', async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto('/');
        await expect(nameLink(page, 'fsrandomizer')).toBeVisible();
        // Collapsed by default here too...
        await expect(nameLink(page, 'foundry-console')).toHaveCount(0);
        await coreToggle(page).click();
        await expect(nameLink(page, 'foundry-console')).toBeVisible();
        // ...and the page never scrolls sideways with the band expanded (the responsive invariant).
        const overflow = await page.evaluate(
            () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow).toBe(0);
    });
});
