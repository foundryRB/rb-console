import { expect, test, type Page } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// INT-FC-R160: the console declares a web app manifest so a device can install it with its
// own icon and name, and declares no service worker. Safari 26 needs no manifest to open a
// Home Screen icon standalone, which is how the console already behaves on a phone; Chromium
// does need one, so without this there is no installed console on Android at all (issue #122).

/** Serve the floor with the /api layer stubbed, so no orchestrator is needed. */
async function openFloor(page: Page) {
    await page.route('**/api/**', (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
    );
    await page.goto('/');
}

interface Manifest {
    id: string;
    start_url: string;
    display: string;
    name: string;
    short_name: string;
    icons: Array<{ src: string; sizes: string; purpose?: string }>;
}

async function readManifest(page: Page): Promise<Manifest> {
    const href = await page.locator('link[rel="manifest"]').getAttribute('href');
    expect(href).not.toBeNull();
    const res = await page.request.get(href ?? '');
    expect(res.ok()).toBe(true);
    return (await res.json()) as Manifest;
}

test.describe('installability', () => {
    intent(
        'INT-FC-R160',
        'the manifest link carries credentials, so the auth proxy cannot swallow it',
        async ({ page }) => {
            await openFloor(page);
            // The manifest is fetched WITHOUT cookies by default, even same-origin. The
            // console is fronted whole by oauth2-proxy, so without this attribute the proxy
            // answers with a login redirect and installability fails with no visible error.
            await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
                'crossorigin',
                'use-credentials',
            );
        },
    );

    intent(
        'INT-FC-R160',
        'the manifest declares a frozen identity and a standalone window',
        async ({ page }) => {
            await openFloor(page);
            const manifest = await readManifest(page);
            // id and start_url are the installed app's identity on the device: changing either
            // forks the icon into a second app the first one's users are never moved to.
            expect(manifest.id).toBe('/');
            expect(manifest.start_url).toBe('/');
            expect(manifest.display).toBe('standalone');
            expect(manifest.short_name).toBe('Console');
        },
    );

    intent(
        'INT-FC-R160',
        'an icon Safari will actually use is present, at both sizes',
        async ({ page }) => {
            await openFloor(page);
            const manifest = await readManifest(page);
            // Safari uses a manifest icon only where `purpose` is absent or includes `any`, so an
            // icon set that is maskable-only is invisible to it.
            const usable = manifest.icons.filter(
                (icon) => icon.purpose === undefined || icon.purpose.split(' ').includes('any'),
            );
            expect(usable.map((icon) => icon.sizes).sort()).toEqual(['192x192', '512x512']);
            for (const icon of manifest.icons) {
                const res = await page.request.get(`/${icon.src}`);
                expect(res.ok(), `${icon.src} is served`).toBe(true);
            }
            // Whichever apple-touch-icon is declared wins over the manifest on Safari, so it has
            // to exist and be served rather than 404 into a screenshot fallback.
            const apple = await page.locator('link[rel="apple-touch-icon"]').getAttribute('href');
            expect(apple).not.toBeNull();
            expect((await page.request.get(apple ?? '')).ok()).toBe(true);
        },
    );

    intent('INT-FC-R160', 'no service worker is registered', async ({ page }) => {
        await openFloor(page);
        // Manifest only, deliberately: the console is a live view of a cluster and has nothing
        // worth showing offline, so it does not take on a cached shell that can outrun a
        // deploy or break the proxy redirect.
        await page.waitForTimeout(500);
        const registrations = await page.evaluate(async () =>
            'serviceWorker' in navigator
                ? (await navigator.serviceWorker.getRegistrations()).length
                : 0,
        );
        expect(registrations).toBe(0);
    });
});
