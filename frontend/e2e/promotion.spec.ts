import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';

// The Promotion cockpit, driven against the stubbed /api layer. It pins what the pane
// must never do: claim a state nothing saw. Every row shows the definitions the contract
// declared (door, terms, acceptance) rather than a shape the pane assumed, an app with no
// contract says so instead of showing an empty queue, and the mode is reachable both by
// deep link and by the masthead toggle that used to be greyed out.

const OVERVIEW = {
    repo: 'example-org/acme-widget',
    exists: true,
    status: 'live',
    phase: null,
    next_skill: null,
    next_command: null,
    blocked_gate: null,
    gates: [],
    records_present: [],
    config: {
        mode: 'interactive',
        provider: 'claude',
        base_url: '',
        model: 'sonnet',
        agent: 'my-claude',
        credentialed: true,
    },
    phases: [],
};

// One target per state the derivation can reach, so the pane is pinned against all of
// them at once: a manual environment behind the proven release, a pair whose door is
// open, an environment carrying it with its probe answering, and one that serves the
// release while the signal it declared says nothing.
const PROMOTION_STATE = {
    repo: 'example-org/acme-widget',
    declared: true,
    problem: '',
    proven: '1.42.0',
    subject: '',
    targets: [
        {
            name: 'example-prod',
            kind: 'environment',
            destination: 'example / prod',
            door: 'commit',
            terms: 'version',
            acceptance: 'probe',
            state: 'pending',
            accepted: '1.39.2',
            door_ref: '',
            detail: '',
            credential: '',
            door_shut: false,
        },
        {
            name: 'partner',
            kind: 'repository',
            destination: 'their-org/their-repo / main',
            door: 'pull-request',
            terms: 'source',
            acceptance: 'none',
            state: 'in-flight',
            accepted: '1.38.0',
            door_ref: 'PR 14',
            detail: '',
            credential: 'partner-pair',
            door_shut: false,
        },
        {
            name: 'chaos-staging',
            kind: 'environment',
            destination: 'chaos / staging',
            door: 'commit',
            terms: 'version',
            acceptance: 'probe',
            state: 'unproven',
            accepted: '1.42.0',
            detail: 'serves 1.42.0, and its declared probe does not answer',
            door_ref: '',
            credential: '',
            door_shut: false,
        },
    ],
};

// What the app could target, read from its own deploy branches. chaos runs a
// single environment, so it IS the entry and offers nothing; example carries two.
const OPTIONS = {
    repo: 'example-org/acme-widget',
    readable: true,
    installs: [
        { install: 'chaos', entry: 'prod', environments: [] },
        { install: 'example', entry: '', environments: ['prod', 'uat'] },
    ],
};

// A pair whose credential the platform does not hold. Its own state rather than a row in
// the shared one: the shared fixture pins that every row carries the definitions its contract
// declared, and a second pull-request door there would make those assertions ambiguous.
const SHUT_DOOR_STATE = {
    repo: 'example-org/acme-widget',
    declared: true,
    problem: '',
    proven: '1.42.0',
    subject: '',
    targets: [
        {
            name: 'acme-portal',
            kind: 'repository',
            destination: 'acme/portal / main',
            door: 'pull-request',
            terms: 'source',
            acceptance: 'none',
            state: 'unreadable',
            accepted: '',
            door_ref: '',
            detail:
                'the door cannot be opened: the platform holds no credential named acme-portal-push',
            credential: 'acme-portal-push',
            door_shut: true,
        },
    ],
};

async function stubApi(page: Page, promotion: unknown = PROMOTION_STATE) {
    await page.route('**/api/**', async (route) => {
        const u = new URL(route.request().url());
        const path = u.pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(contractFixture(data, [])),
            });
        switch (path) {
            case '/fleet':
                return body({ projects: [] });
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({ agents: [] });
            case '/runs':
                return body({ runs: [] });
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(OVERVIEW);
            case '/deliveries/config':
                return body(OVERVIEW.config);
            case '/promotion/state':
                return body(promotion);
            case '/promotion/options':
                return body(OPTIONS);
            case '/promotion/target':
                return body({
                    target: 'partner',
                    commit: 'abc1234',
                    repo: 'example-org/acme-widget',
                    declared: true,
                    problem: '',
                    proven: '1.42.0',
                    subject: '',
                    targets: [
                        {
                            name: 'partner',
                            kind: 'repository',
                            destination: 'their-org/their-repo / main',
                            door: 'pull-request',
                            terms: 'source',
                            acceptance: 'none',
                            state: 'pending',
                            accepted: '',
                            door_ref: '',
                            detail: '',
                            credential: 'partner-pair',
                            door_shut: false,
                        },
                    ],
                });
            default:
                return body({});
        }
    });
}

test.describe('promotion cockpit', () => {
    test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 900 });
    });

    test('every row carries the definitions its contract declared', async ({ page }) => {
        await stubApi(page);
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');

        // The proven release is the promotion's input, shown once.
        await expect(page.getByText('Proven release')).toBeVisible();
        await expect(page.getByText('1.42.0').first()).toBeVisible();

        // An environment target: our commit, the version, and where it stands.
        await expect(page.getByText('example-prod', { exact: true })).toBeVisible();
        await expect(page.getByText('example / prod · environment')).toBeVisible();
        await expect(page.getByText('door: commit').first()).toBeVisible();
        await expect(page.getByText('terms: version').first()).toBeVisible();
        await expect(page.getByText('1.39.2')).toBeVisible();
        await expect(page.getByText('pending')).toBeVisible();
        // Pending names the act rather than performing it: the skill is the act.
        await expect(page.getByText('promote example-org/acme-widget example-prod')).toBeVisible();

        // A pair target: their door, source terms, and the door in flight by name.
        await expect(page.getByText('door: pull-request')).toBeVisible();
        await expect(page.getByText('terms: source')).toBeVisible();
        await expect(page.getByText('in flight')).toBeVisible();
        await expect(page.getByText('PR 14 awaits their review')).toBeVisible();
    });

    test('a target that serves the release without answering is not called current', async ({
        page,
    }) => {
        await stubApi(page);
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        // The row carries the proven release AND says unproven: unchecked is not proven,
        // and the reason the backend derived rides along rather than being re-invented.
        await expect(page.getByText('unproven')).toBeVisible();
        await expect(
            page.getByText('serves 1.42.0, and its declared probe does not answer'),
        ).toBeVisible();
    });

    test('an app with no contract says so instead of showing an empty queue', async ({
        page,
    }) => {
        await stubApi(page, {
            repo: 'example-org/acme-widget',
            declared: false,
            problem: '',
            proven: '',
            targets: [],
        });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await expect(page.getByText('No promotion contract')).toBeVisible();
        await expect(page.getByText('devops/promotion.yaml')).toBeVisible();
    });

    test('a malformed contract reports the malformation', async ({ page }) => {
        await stubApi(page, {
            repo: 'example-org/acme-widget',
            declared: true,
            problem: "target 'example-prod' is declared twice",
            proven: '1.42.0',
            targets: [],
        });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await expect(
            page.getByText("The contract is malformed: target 'example-prod' is declared twice"),
        ).toBeVisible();
    });

    test('the masthead toggle reaches the mode, not only the deep link', async ({ page }) => {
        await stubApi(page);
        await page.goto('/d?repo=example-org%2Facme-widget');
        // The button was greyed and disabled before the third mode existed.
        const promotion = page.getByRole('button', { name: 'Promotion' });
        await expect(promotion).toBeEnabled();
        await promotion.click();
        await expect(page.getByText('example-prod', { exact: true })).toBeVisible();
    });

    test('an app with no contract can declare its first target', async ({ page }) => {
        await stubApi(page, {
            repo: 'example-org/acme-widget',
            declared: false,
            problem: '',
            proven: '',
            targets: [],
        });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await page.getByRole('button', { name: 'Declare a target' }).click();

        // The pair kind needs nothing from the platform: repo, branch, credential NAME.
        await page.getByRole('button', { name: "Another organization's repo" }).click();
        await page.getByPlaceholder('example-uat').fill('partner');
        await page.getByPlaceholder('their-org/their-repo').fill('their-org/their-repo');
        await page.getByPlaceholder('partner-pair').fill('partner-pair');
        // The form says plainly that the secret never enters the contract.
        await expect(page.getByText('the platform holds the secret')).toBeVisible();

        await page.getByRole('button', { name: 'Declare target' }).click();
        // The pane comes back carrying the row the act just wrote.
        await expect(page.getByText('partner', { exact: true })).toBeVisible();
        await expect(page.getByText('their-org/their-repo / main · repository')).toBeVisible();
    });

    test('an install running one environment offers none, and says why', async ({ page }) => {
        await stubApi(page, {
            repo: 'example-org/acme-widget',
            declared: false,
            problem: '',
            proven: '',
            targets: [],
        });
        // The fleet as it stands: every install this app runs on declares one
        // environment, and that one is the entry.
        await page.route('**/api/promotion/options*', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    repo: 'example-org/acme-widget',
                    readable: true,
                    installs: [{ install: 'chaos', entry: 'prod', environments: [] }],
                }),
            }),
        );
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await page.getByRole('button', { name: 'Declare a target' }).click();
        // chaos deploys into its only environment automatically, so nothing there
        // can be a promotion target: the form explains rather than offering it.
        await expect(
            page.getByText('Every install this app runs on declares a single environment'),
        ).toBeVisible();
    });

    test('a Managed app is not a promotion subject, and no row offers the act', async ({
        page,
    }) => {
        // Adopt declares a Managed app's HOME in its promotion contract, so the pane sees a
        // repository target. Left to the derivation it read PENDING (nothing proven compares
        // unequal to anything) and offered Promote on an app promotion never reaches.
        await stubApi(page, {
            repo: 'example-org/acme-widget',
            declared: true,
            problem: '',
            proven: '',
            subject: 'managed',
            targets: [],
        });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await expect(page.getByText('Managed: not a promotion subject')).toBeVisible();
        await expect(page.getByRole('button', { name: 'Promote' })).toHaveCount(0);
    });

    test('a shut door reads as one, and offers registration rather than the act', async ({
        page,
    }) => {
        // Issue #131 as a surface: before this, a target whose credential the platform did
        // not hold rendered exactly like one that works, because nothing tried. The row must
        // say the door is shut, name the credential to register, and offer NO Promote button -
        // a promotion that cannot be performed must never look like one that can.
        await stubApi(page, SHUT_DOOR_STATE);
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await expect(page.getByText('door shut')).toBeVisible();
        await expect(page.getByText(/no credential named acme-portal-push/)).toBeVisible();
        await expect(page.getByText(/register acme-portal-push in Settings/)).toBeVisible();
        await expect(page.getByRole('button', { name: 'Promote' })).toHaveCount(0);
    });

    test('a target that is behind offers the act, and its receipt names the run', async ({
        page,
    }) => {
        // The console DRIVES the promote skill rather than printing its name: the door is
        // performed by a worker, because a pair door pushes a tree with a credential no HTTP
        // door returns the value of.
        await stubApi(page);
        let driven: Record<string, unknown> | null = null;
        await page.route('**/api/promotion/drive', async (route) => {
            driven = route.request().postDataJSON() as Record<string, unknown>;
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    run_id: 'p-abc123',
                    handle: 'wf-1',
                    target: 'example-prod',
                    release: '1.42.0',
                    kind: 'environment',
                }),
            });
        });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await page.getByRole('button', { name: 'Promote' }).click();
        await expect(page.getByText(/driving 1\.42\.0 · run p-abc123/)).toBeVisible();
        expect(driven).toMatchObject({ repo: 'example-org/acme-widget', target: 'example-prod' });
    });

    test('a drive the console refuses is shown on the row it was refused for', async ({
        page,
    }) => {
        // Every promotion refusal is raised before a pod exists, because each one is
        // something the operator can act on. It must land on ITS row: the pane shows several,
        // and a bare message would render under all of them at once.
        await stubApi(page);
        await page.route('**/api/promotion/drive', (route) =>
            route.fulfill({
                status: 422,
                contentType: 'application/json',
                body: JSON.stringify({
                    detail:
                        'this app has no entry environment, so it is Managed: nothing here can prove a release live',
                }),
            }),
        );
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await page.getByRole('button', { name: 'Promote' }).click();
        await expect(page.getByText(/it is Managed/)).toBeVisible();
    });

    test('a refusal from the door is shown where the operator is', async ({ page }) => {
        await stubApi(page, {
            repo: 'example-org/acme-widget',
            declared: false,
            problem: '',
            proven: '',
            targets: [],
        });
        await page.route('**/api/promotion/target', (route) =>
            route.fulfill({
                status: 422,
                contentType: 'application/json',
                body: JSON.stringify({
                    detail:
                        "chaos's prod is its entry environment: it is deployed automatically, so a promotion into it would be overwritten by the next release",
                }),
            }),
        );
        await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
        await page.getByRole('button', { name: 'Declare a target' }).click();
        await page.getByPlaceholder('example-uat').fill('chaos-prod');
        await page.getByRole('button', { name: 'Declare target' }).click();
        await expect(page.getByText(/entry environment/)).toBeVisible();
    });
});


test('a compiled promotion receipt belongs to its exact originating repository', async ({ page }) => {
    const compiled = JSON.parse(execFileSync(process.env.PYTHON ?? 'python', [
        path.resolve('e2e/compiled_runs_fixture.py'), OVERVIEW.repo, 'p-source', 'Running', 'promotion',
    ], { encoding: 'utf8' }));
    const target = { ...PROMOTION_STATE.targets[0], name: compiled.promotion };
    await stubApi(page, { ...PROMOTION_STATE, targets: [target] });
    await page.route('**/api/promotion/state*', async (route) => {
        const repo = new URL(route.request().url()).searchParams.get('repo');
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...PROMOTION_STATE, repo, targets: [target] }) });
    });
    await page.route('**/api/promotion/drive', async (route) => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ run_id: compiled.run_id, handle: compiled.handle, target: compiled.promotion, release: '1.42.0', kind: 'environment' }) });
    });
    await page.goto('/d?repo=example-org%2Facme-widget&mode=promotion');
    await page.getByRole('button', { name: 'Promote', exact: true }).click();
    await expect(page.getByText(/driving 1\.42\.0 · run p-source/)).toBeVisible();
    await page.evaluate(() => {
        history.pushState({}, '', '/d?repo=other-org%2Facme-widget&mode=promotion');
        dispatchEvent(new PopStateEvent('popstate'));
    });
    await page.getByRole('button', { name: 'Promotion', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Promote', exact: true })).toBeVisible();
    await expect(page.getByText(/driving 1\.42\.0 · run p-source/)).toHaveCount(0);
});
