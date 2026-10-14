import { contractFixture } from './contract-fixture';
import { expect, test, type Page } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// INT-FC-R159: Settings carries a Session card, last in the column, whose Sign out control is a
// plain full-page navigation to the sign-in proxy's own route - and carries it only where the
// OIDC gate fronts the install. The console installed to a phone's Home Screen has no address
// bar, so this card is the only way its session can be ended from inside the app (issue #120).

const SIGN_OUT = '/oauth2/sign_out';

/** Serve Settings with the /api layer stubbed, the session door answering `session`. */
async function openSettings(page: Page, session: unknown) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        switch (path) {
            case '/config/session':
                if (session === null) {
                    // The door unreachable: the card must stay away rather than guess a gate.
                    return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
                }
                return body(session);
            case '/config/git-identities':
                return body({ identities: [] });
            case '/config/git-roles':
                return body({ roles: {}, catalog: [] });
            case '/config/pair-credentials':
                return body({ credentials: [] });
            case '/config/mcp-doors':
                return body({ doors: [] });
            case '/agents':
                return body({ agents: [] });
            case '/fleet':
                return body({ projects: [] });
            default:
                return body({});
        }
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
}

const signOut = (page: Page) => page.getByRole('link', { name: 'Sign out', exact: true });

test.describe('Settings can end the session it is served behind (INT-FC-R159)', () => {
    intent('INT-FC-R159', 'behind the gate, the Session card is last in the column', async ({ page }) => {
        await openSettings(page, { oidc_enabled: true, sign_out_url: SIGN_OUT });
        await expect(page.getByRole('heading', { name: 'Session', exact: true })).toBeVisible();
        // Each card of the column titles itself with an h3, so the last one is the last card.
        await expect(page.locator('h3').last()).toHaveText('Session');
    });

    intent('INT-FC-R159', 'Sign out is an anchor at the route the door named', async ({ page }) => {
        await openSettings(page, { oidc_enabled: true, sign_out_url: SIGN_OUT });
        // A link, not a button: the route is the proxy's, so pressing it is a navigation.
        await expect(signOut(page)).toHaveAttribute('href', SIGN_OUT);
    });

    intent('INT-FC-R159', 'pressing it LEAVES the SPA for the proxy, not a client route', async ({ page }) => {
        // The proxy is not in front of the dev server, so stand in for it. If the control were a
        // react-router Link this request would never be made at all - the app shell would swallow
        // the path client-side - and if it were a fetch the tab would not move. Both show up here.
        await page.route(`**${SIGN_OUT}`, (route) =>
            route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>the proxy answered</h1>' }),
        );
        await openSettings(page, { oidc_enabled: true, sign_out_url: SIGN_OUT });

        await signOut(page).click();
        await expect(page).toHaveURL(new RegExp(`${SIGN_OUT}$`));
        await expect(page.getByRole('heading', { name: 'the proxy answered' })).toBeVisible();
    });

    intent('INT-FC-R159', 'an install with no gate is offered no sign-out', async ({ page }) => {
        await openSettings(page, { oidc_enabled: false, sign_out_url: '' });
        await expect(page.getByRole('heading', { name: 'Session', exact: true })).toHaveCount(0);
        await expect(signOut(page)).toHaveCount(0);
    });

    intent('INT-FC-R159', 'a door that will not answer offers no sign-out either', async ({ page }) => {
        await openSettings(page, null);
        await expect(page.getByRole('heading', { name: 'Session', exact: true })).toHaveCount(0);
    });
});
