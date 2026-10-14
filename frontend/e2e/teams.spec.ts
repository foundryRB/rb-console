import { contractFixture } from './contract-fixture';
import { expect, test, type Page, type Request } from '@playwright/test';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// INT-FC-R183, INT-FC-R185, INT-FC-R186: with teams on, Settings offers the Teams card to an
// admin alone, each saved provider says whom it serves and is editable only by who may change
// it, and a new delivery belongs to a team the caller chooses from its own.

const ADMIN = {
    oidc_enabled: true,
    sign_out_url: '/oauth2/sign_out',
    teams_enabled: true,
    admin: true,
    teams: [],
    user: 'root@example.org',
};
const MEMBER = { ...ADMIN, admin: false, teams: ['alpha', 'beta'], user: 'dave@example.org' };

const TEAMS = [
    { name: 'alpha', group: 'team-alpha', repositories: ['example-org/alpha-shop'] },
    { name: 'beta', group: 'team-beta', repositories: [] },
];

const AGENTS = [
    { name: 'Install key', provider: 'claude', base_url: '', model: 'm', models: ['m'], configured: true, level: 'install', owner: '', usable: true, manageable: false },
    { name: 'Alpha seat', provider: 'claude', base_url: '', model: 'm', models: ['m'], configured: true, level: 'team', owner: 'alpha', usable: true, manageable: true },
];

const project = (repo: string) => ({
    repo, name: repo.split('/')[1], is_delivery: false, delivery_status: null, delivery_phase: null,
    onboarded: false, live: null, updated: 't', estimatekit: false, protopane: false, hidden: false,
    role: null, activity: null,
});

/** Serve the app with the /api layer stubbed, recording every command body. */
async function serve(page: Page, session: unknown, sent: { path: string; body: unknown }[] = []) {
    await page.route('**/api/**', async (route) => {
        const request: Request = route.request();
        const path = new URL(request.url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, [])) });
        if (request.method() !== 'GET') {
            sent.push({ path, body: request.postDataJSON() });
            return body({ repo: 'example-org/gamma-app', exists: true, status: 'scope', phases: [], gates: [], records_present: [] });
        }
        switch (path) {
            case '/config/session':
                return body(session);
            case '/config/teams':
                return body({ teams: TEAMS });
            case '/config/git-identities':
                return body({ identities: [] });
            case '/config/git-roles':
                return body({ roles: {}, catalog: [] });
            case '/config/pair-credentials':
                return body({ credentials: [] });
            case '/config/mcp-doors':
                return body({ doors: [] });
            case '/agents':
                return body({ agents: AGENTS });
            case '/fleet':
                return body({ projects: [project('example-org/alpha-shop'), project('example-org/loose-ends')] });
            case '/maintenance/inbox':
                return body({ items: [], scanned: true });
            case '/studios':
                return body({ studios: [] });
            case '/runs':
                return body({ runs: [] });
            default:
                return body({});
        }
    });
    await page.setViewportSize({ width: 1280, height: 900 });
}

test.describe('teams on one install', () => {
    intent('INT-FC-R183', 'an admin sets up the teams in Settings; a member is offered no Teams card', async ({ page }) => {
        await serve(page, ADMIN);
        await page.goto('/settings');
        await expect(page.getByRole('heading', { name: 'Teams', exact: true })).toBeVisible();
        await expect(page.getByText('group team-alpha')).toBeVisible();
        await expect(page.getByText('Visible to admins only: example-org/loose-ends')).toBeVisible();

        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await serve(page, MEMBER);
        await page.goto('/settings');
        await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
        await expect(page.getByRole('heading', { name: 'Teams', exact: true })).toHaveCount(0);
        // The installation-wide settings are an admin's: a member is not offered them.
        await expect(page.getByRole('heading', { name: 'Pair credentials', exact: true })).toHaveCount(0);
        await expect(page.getByText('an admin sets them')).toBeVisible();
    });

    intent('INT-FC-R186', 'each saved provider says whom it serves, and only its managers edit it', async ({ page }) => {
        const sent: { path: string; body: unknown }[] = [];
        await serve(page, MEMBER, sent);
        await page.goto('/settings');
        await expect(page.getByText('team alpha', { exact: true })).toBeVisible();
        await expect(page.getByText('install', { exact: true })).toBeVisible();
        const rows = page.getByRole('button', { name: 'Edit', exact: true });
        await expect(rows.nth(0)).toBeDisabled();
        await expect(rows.nth(1)).toBeEnabled();

        // A member saves for one of its teams or for itself; the install level is not offered.
        const level = page.getByTitle('Who may apply this agent to a line');
        await expect(level.locator('option')).toHaveText(['Team alpha', 'Team beta', 'Only me']);
        await page.getByPlaceholder('name (e.g. My Claude sub)').fill('Beta seat');
        await page.getByPlaceholder('setup-token or API key').fill('beta-key');
        await level.selectOption('team:beta');
        await page.getByRole('button', { name: 'Save provider' }).click();
        await expect.poll(() => sent.find((s) => s.path === '/agents')?.body).toMatchObject({
            name: 'Beta seat', level: 'team', team: 'beta',
        });
    });

    intent('INT-FC-R185', 'a member of several teams chooses the team a new delivery belongs to', async ({ page }) => {
        const sent: { path: string; body: unknown }[] = [];
        await serve(page, MEMBER, sent);
        await page.goto('/');
        await page.getByRole('button', { name: 'New delivery' }).click();
        await page.getByPlaceholder('acme-store').first().fill('gamma-app');
        const submit = page.getByRole('button', { name: 'Establish delivery' });
        await expect(submit).toBeDisabled();
        await page.getByLabel('Team').selectOption('beta');
        await submit.click();
        await expect.poll(() => sent.find((s) => s.path === '/establish')?.body).toMatchObject({
            target: 'gamma-app', team: 'beta',
        });
    });
});
