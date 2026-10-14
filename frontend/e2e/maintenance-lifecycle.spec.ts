import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';
import { localEditorNetwork } from './editor-network';
import { intent } from '@psa-department-of-engineering/playwright-intent';

// The Maintenance ticket-line cockpit, driven against the stubbed /api layer. It pins the
// reshape: the backlog is a ticket picker; opening a ticket shows its line (State) as the
// spine, the selected stop's content (Substance), and the ticket's next act (Action) - so a
// merge-ready ticket shows the Merge button ON the line (the reported bug), and a stalled one
// shows Re-drive instead of dead-ending.

const OVERVIEW = {
    repo: 'example-org/acme-widget',
    exists: true,
    status: 'run-phase',
    phase: 'build+ship',
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

// #5 was resolved by a run marked Succeeded, but no PR exists (the stall). #7 was resolved
// cleanly: an open PR, a PASS verdict, green checks - merge-ready.
const MAINT_STATE = {
    repo: 'example-org/acme-widget',
    positions: {
        repo: 'example-org/acme-widget',
        issues: [
            {
                number: 5,
                title: 'PT-PT audio labels',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/5',
                created_at: '',
                // The author tagged this one heavy + urgent (its issue body carried the markers);
                // the picker rail must show a full complexity meter and the double-up arrow.
                complexity: 'high',
                priority: 'highest',
                // and it carries the native GitHub Issue Type Bug -> a Type badge.
                type: 'Bug',
            },
            {
                number: 7,
                title: 'Fix the thing',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/7',
                created_at: '',
                complexity: 'medium',
                priority: 'low',
            },
            {
                number: 8,
                title: 'Merged already',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/8',
                created_at: '',
            },
            // #9 was NEVER driven in THIS repo - only another repo has a resolve run for ticket 9.
            {
                number: 9,
                title: 'Never driven here',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/9',
                created_at: '',
            },
            // #10 has an open PR its fresh-eyes review FAILed - the dead-end this repo used to hit.
            {
                number: 10,
                title: 'Broken thing',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/10',
                created_at: '',
            },
            // #11 is being driven ONE-SHOT: its resolve run (with a folded review step) is live and
            // its PR awaits the engine's verdict-driven merge.
            {
                number: 11,
                title: 'One-shot in flight',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/11',
                created_at: '',
            },
            // #12's PR was reviewed by its own author: the review ends VERDICT: UNRECORDED, so it
            // records neither PASS nor FAIL and waits for an independent reviewer.
            {
                number: 12,
                title: 'Self-reviewed thing',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/12',
                created_at: '',
            },
            // #13's PR carries a verdict string the console does not know.
            {
                number: 13,
                title: 'Unknown verdict thing',
                author: 'rafaelgpires',
                labels: [],
                url: 'https://x/13',
                created_at: '',
            },
        ],
        prs: [
            {
                number: 14,
                title: 'feat(#7): fix the thing',
                author: 'rafaelgpires',
                head: 'feat/7-fix-the-thing',
                head_sha: 'abc',
                url: 'https://x/pr/14',
                verdict: 'pass',
                checks: 'green',
                contributor: false,
                updated_at: '',
                state: 'open',
            },
            {
                number: 20,
                title: 'feat(#10): broken thing',
                author: 'rafaelgpires',
                head: 'feat/10-broken-thing',
                head_sha: 'bbb',
                url: 'https://x/pr/20',
                verdict: 'fail',
                checks: 'red',
                contributor: false,
                updated_at: '',
                state: 'open',
            },
            {
                number: 21,
                title: 'feat(#11): one-shot thing',
                author: 'rafaelgpires',
                head: 'feat/11-one-shot-thing',
                head_sha: 'ccc',
                url: 'https://x/pr/21',
                verdict: 'awaiting',
                checks: 'green',
                contributor: false,
                updated_at: '',
                state: 'open',
            },
            {
                number: 22,
                title: 'feat(#12): self-reviewed thing',
                author: 'rafaelgpires',
                head: 'feat/12-self-reviewed-thing',
                head_sha: 'eee',
                url: 'https://x/pr/22',
                verdict: 'unrecorded',
                checks: 'green',
                contributor: false,
                updated_at: '',
                state: 'open',
            },
            {
                number: 23,
                title: 'feat(#13): unknown verdict thing',
                author: 'rafaelgpires',
                head: 'feat/13-unknown-verdict-thing',
                head_sha: 'fff',
                url: 'https://x/pr/23',
                verdict: 'stale',
                checks: 'green',
                contributor: false,
                updated_at: '',
                state: 'open',
            },
        ],
        // #8's PR already merged but did not auto-close the ticket - the merged-aware path.
        recent_closed: [
            {
                number: 16,
                title: 'feat(#8): done',
                author: 'rafaelgpires',
                head: 'feat/8-done',
                head_sha: 'd',
                url: 'https://x/pr/16',
                verdict: 'awaiting',
                checks: 'unknown',
                contributor: false,
                updated_at: '',
                state: 'merged',
            },
        ],
        train: {
            version: '2.10.3',
            unreleased_total: 0,
            breaking: 0,
            feat: 0,
            fix: 0,
            other: 0,
            next_version: '',
            deployed: '',
            healthy: null,
        },
    },
    action: {
        acts: ['resolve', 'review', 'reconcile-docs'],
        modes: ['gated', 'one-shot', 'direct'],
        default_mode: 'gated',
    },
    delivery: { status: 'run-phase', phase: 'build+ship' },
    // The engine is watching #11's one-shot drive (not yet acted): it will merge on a recorded
    // PASS with green checks, re-drive on a FAIL, or park the PR for the operator.
    driven: [
        {
            handle: 'live:workflow.argoproj.io/m-os110001',
            repo: 'example-org/acme-widget',
            ticket: 11,
            acted: false,
            result: '',
        },
    ],
};

const RUNS = [
    // A review run in flight for #7's PR (#14). The Verdict stop must SURFACE it - live status,
    // node band, Stop / Terminate - instead of the old "no review yet" over a running worker.
    {
        handle: 'live:workflow.argoproj.io/maint-review-acme-widget-rvw01',
        name: 'maint-review-acme-widget-rvw01',
        run_id: 'm-rev14001',
        mode: 'gated',
        maintenance: 'review',
        ticket: '14',
        repo: OVERVIEW.repo,
        repo_slug: 'acme-widget',
        phase: 'Running',
        created: '2026-07-12T20:00:00Z',
        started: '2026-07-12T20:00:05Z',
        finished: null,
    },
    // A ONE-SHOT drive for #11: a single resolve Workflow whose second step reviews the PR (no
    // separate review Workflow). Its review must be watchable at the Review stop too - not only
    // at Resolve - and the engine's merge shown at the Merge stop.
    {
        handle: 'live:workflow.argoproj.io/maint-resolve-acme-widget-osrun1',
        name: 'maint-resolve-acme-widget-osrun1',
        run_id: 'm-os110001',
        mode: 'one-shot',
        maintenance: 'resolve',
        ticket: '11',
        repo: OVERVIEW.repo,
        repo_slug: 'acme-widget',
        phase: 'Running',
        created: '2026-07-12T21:00:00Z',
        started: '2026-07-12T21:00:05Z',
        finished: null,
    },
    {
        handle: 'live:workflow.argoproj.io/maint-resolve-acme-widget-frpgb',
        name: 'maint-resolve-acme-widget-frpgb',
        run_id: 'm-e4e94170',
        mode: 'gated',
        maintenance: 'resolve',
        ticket: '5',
        repo: OVERVIEW.repo,
        repo_slug: 'acme-widget',
        phase: 'Succeeded',
        created: '2026-07-12T19:04:08Z',
        started: null,
        finished: null,
    },
    {
        handle: 'live:workflow.argoproj.io/maint-resolve-acme-widget-aaaaa',
        name: 'maint-resolve-acme-widget-aaaaa',
        run_id: 'm-11111111',
        mode: 'gated',
        maintenance: 'resolve',
        ticket: '7',
        repo: OVERVIEW.repo,
        repo_slug: 'acme-widget',
        phase: 'Succeeded',
        created: '2026-07-12T18:00:00Z',
        started: null,
        finished: null,
    },
    {
        handle: 'live:workflow.argoproj.io/maint-resolve-acme-widget-bbbbb',
        name: 'maint-resolve-acme-widget-bbbbb',
        run_id: 'm-22222222',
        mode: 'gated',
        maintenance: 'resolve',
        ticket: '10',
        repo: OVERVIEW.repo,
        repo_slug: 'acme-widget',
        phase: 'Succeeded',
        created: '2026-07-12T17:00:00Z',
        started: null,
        finished: null,
    },
    // A resolve run for ticket #9 in ANOTHER repo. It must NOT leak into acme-widget's #9 line
    // (the phantom-run bug): matched by act + number alone, it read as "acme-widget #9 resolved".
    {
        handle: 'live:workflow.argoproj.io/maint-resolve-other-repo-ccccc',
        name: 'maint-resolve-other-repo-ccccc',
        run_id: 'm-33333333',
        mode: 'gated',
        maintenance: 'resolve',
        ticket: '9',
        repo: 'other-org/acme-widget',
        repo_slug: 'acme-widget',
        phase: 'Succeeded',
        created: '2026-07-12T16:00:00Z',
        started: null,
        finished: null,
    },
].map((spec) => ({
    ...spec,
    ...JSON.parse(execFileSync(process.env.PYTHON ?? 'python', [
        path.resolve('e2e/compiled_runs_fixture.py'), spec.repo, spec.run_id, spec.phase,
        'maintenance', spec.maintenance, spec.ticket, spec.mode,
    ], { encoding: 'utf8' })),
}));

// Prepare pure contract projections before browser assertions start their timeout.
contractFixture(OVERVIEW, RUNS);
contractFixture(MAINT_STATE, RUNS);

async function stubApi(page: Page) {
    await page.route('**/api/**', async (route) => {
        const u = new URL(route.request().url());
        const path = u.pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(contractFixture(data, RUNS)),
            });
        switch (path) {
            case '/fleet':
                return body({ projects: [] });
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({
                    agents: [
                        {
                            name: 'my-claude',
                            provider: 'claude',
                            base_url: '',
                            model: 'sonnet',
                            models: ['sonnet'],
                            configured: true,
                        },
                    ],
                });
            case '/maintenance/inbox':
                return body({ items: [], scanned: true });
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(OVERVIEW);
            case '/deliveries/config':
                return body(OVERVIEW.config);
            case '/maintenance/state':
                return body(MAINT_STATE);
            case '/runs':
                return body({ runs: RUNS });
            case '/runs/graph': {
                const h = u.searchParams.get('handle') ?? '';
                const name = h.startsWith('live:') ? (h.split('/').pop() ?? '') : h;
                const reviewNode = (phase: string) => ({
                    id: 'n-review',
                    name: 'review',
                    type: 'Pod',
                    phase,
                    template: 'worker-review',
                    message: '',
                    children: [],
                    startedAt: '2026-07-12T20:00:05Z',
                    finishedAt: null,
                    artifacts: [],
                });
                const resolveNode = (phase: string) => ({
                    id: 'n-resolve',
                    name: 'resolve',
                    type: 'Pod',
                    phase,
                    template: 'worker-resolve',
                    message: '',
                    children: [],
                    startedAt: '2026-07-12T21:00:05Z',
                    finishedAt: '2026-07-12T21:03:00Z',
                    artifacts: [],
                });
                if (RUNS.find((run) => run.name === name)?.maintenance === 'review')
                    return body({
                        name,
                        phase: 'Running',
                        progress: '1/1',
                        nodes: [reviewNode('Running')],
                    });
                // The one-shot resolve run: resolve done, review live - the second step reviews the PR.
                if (RUNS.find((run) => run.name === name)?.mode === 'one-shot')
                    return body({
                        name,
                        phase: 'Running',
                        progress: '2/2',
                        nodes: [resolveNode('Succeeded'), reviewNode('Running')],
                    });
                return body({
                    name,
                    phase: 'Succeeded',
                    progress: '1/1',
                    nodes: [resolveNode('Succeeded')],
                });
            }
            case '/runs/logs':
                return body({
                    handle: u.searchParams.get('handle'),
                    logs: 'fresh-eyes worker booting…',
                });
            case '/maintenance/substance': {
                const kind = u.searchParams.get('kind');
                const id = Number(u.searchParams.get('id'));
                if (kind === 'pr' && id === 22)
                    return body({
                        kind: 'pr',
                        number: id,
                        title: 'feat(#12): self-reviewed thing',
                        author: 'rafaelgpires',
                        head: 'feat/12-self-reviewed-thing',
                        url: `https://x/pr/${id}`,
                        verdict: 'unrecorded',
                        checks: 'green',
                        files: [],
                        reviews: [
                            {
                                author: 'rafaelgpires',
                                submitted_at: '2026-07-12',
                                body: 'Reads clean, but I opened this PR.\nVERDICT: UNRECORDED',
                            },
                        ],
                    });
                if (kind === 'pr')
                    return body({
                        kind: 'pr',
                        number: id,
                        title: 'feat(#7): fix the thing',
                        author: 'rafaelgpires',
                        head: 'feat/7-fix-the-thing',
                        url: `https://x/pr/${id}`,
                        verdict: 'pass',
                        checks: 'green',
                        files: [
                            {
                                filename: 'src/thing.ts',
                                status: 'modified',
                                additions: 3,
                                deletions: 1,
                                patch: '@@ -1 +1 @@\n-old\n+new',
                            },
                        ],
                        reviews: [
                            {
                                author: 'reviewer',
                                submitted_at: '2026-07-12',
                                body: 'looks good\nVERDICT: PASS',
                            },
                        ],
                    });
                return body({
                    kind: 'issue',
                    number: id,
                    title: id === 5 ? 'PT-PT audio labels' : 'Fix the thing',
                    body: `Body of #${id}`,
                    url: `https://x/${id}`,
                });
            }
            default:
                return body({});
        }
    });
}

const row = (page: Page, title: string) => page.getByRole('button').filter({ hasText: title });
const stop = (page: Page, label: string) => page.getByRole('tab').filter({ hasText: label });

test.describe('maintenance ticket cockpit', () => {
    test.beforeEach(async ({ page }) => {
        await stubApi(page);
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=maintenance');
        // The picker lists the open backlog.
        await expect(page.getByText('PT-PT audio labels')).toBeVisible();
        await expect(page.getByText('Fix the thing')).toBeVisible();
    });

    test('the backlog picker flags each ticket by where it sits', async ({ page }) => {
        // #5 is stalled (resolve went green, no PR); #7 sits at merge.
        await expect(
            row(page, 'PT-PT audio labels').getByText('stalled', { exact: true }),
        ).toBeVisible();
        await expect(
            row(page, 'Fix the thing').getByText('at merge', { exact: true }),
        ).toBeVisible();
        // No line yet - the picker is master, the cockpit is detail.
        await expect(page.getByRole('tablist')).toHaveCount(0);
    });

    test('a tagged ticket shows its complexity meter, priority arrow + type badge; a clean one shows none', async ({
        page,
    }) => {
        // #5 carries Complexity: High / Priority: Highest - both signals render in the picker rail.
        await expect(row(page, 'PT-PT audio labels').getByTitle('Priority: Highest')).toBeVisible();
        await expect(
            row(page, 'PT-PT audio labels').getByTitle(/Complexity: high/),
        ).toBeVisible();
        // #7 carries the mid scale.
        await expect(row(page, 'Fix the thing').getByTitle('Priority: Low')).toBeVisible();
        await expect(row(page, 'Fix the thing').getByTitle(/Complexity: medium/)).toBeVisible();
        // #5 also carries the native GitHub Issue Type -> a Type badge.
        await expect(row(page, 'PT-PT audio labels').getByTitle(/Type: Bug/)).toBeVisible();
        // #8 carries no marker or type - no arrow, no meter, no type badge (the clean-repo case).
        await expect(row(page, 'Merged already').getByTitle(/Priority:/)).toHaveCount(0);
        await expect(row(page, 'Merged already').getByTitle(/Complexity:/)).toHaveCount(0);
        await expect(row(page, 'Merged already').getByTitle(/Type:/)).toHaveCount(0);
        // The signals follow the ticket into its cockpit header when opened.
        await row(page, 'PT-PT audio labels').click();
        await expect(page.getByTitle('Priority: Highest')).toBeVisible();
        await expect(page.getByTitle(/Complexity: high/)).toBeVisible();
        await expect(page.getByTitle(/Type: Bug/)).toBeVisible();
    });

    test('opening a merge-ready ticket puts the Merge button ON the line', async ({ page }) => {
        await row(page, 'Fix the thing').click();
        // The line is the spine, with the four stops (PR + Verdict collapsed into Review).
        await expect(page.getByRole('tablist')).toBeVisible();
        for (const label of ['Ticket', 'Resolve', 'Review', 'Merge']) {
            await expect(stop(page, label).first()).toBeVisible();
        }
        // Neither the old separate PR nor Verdict stop remains.
        await expect(stop(page, 'Verdict')).toHaveCount(0);
        // The reported bug, fixed: the Merge action is right here, not on another tab.
        await expect(page.getByRole('button', { name: /Merge #14/ })).toBeVisible();
    });

    test('a stalled ticket shows Re-drive, not a dead end', async ({ page }) => {
        await row(page, 'PT-PT audio labels').click();
        // A green resolve with no PR visible (open or recently-closed) reads Review = verify
        // (stalled), and the act is Re-drive, not a missing button.
        await expect(
            stop(page, 'Review').first().getByText('verify', { exact: true }),
        ).toBeVisible();
        await expect(page.getByRole('button', { name: /Re-drive #5/ })).toBeVisible();
    });

    test('a merged ticket shows Close and PR merged, not Re-drive / No PR', async ({ page }) => {
        await row(page, 'Merged already').click();
        // The centre reads the merged PR (merged-aware), not "No PR to merge yet".
        await expect(page.getByText('PR #16 merged', { exact: true })).toBeVisible();
        // The act is Close (the merge did not auto-close it), never a meaningless Re-drive.
        await expect(page.getByRole('button', { name: /Close #8/ })).toBeVisible();
        await expect(page.getByRole('button', { name: /Re-drive #8/ })).toHaveCount(0);
    });

    test('selecting a stop changes the substance', async ({ page }) => {
        await row(page, 'Fix the thing').click();
        // The Ticket stop shows the issue body.
        await stop(page, 'Ticket').first().click();
        await expect(page.getByText('Body of #7')).toBeVisible();
        // The Review stop shows the PR diff (the changed file) - the old PR stop's substance,
        // now under Review alongside the verdict.
        await stop(page, 'Review').first().click();
        await expect(page.getByText('src/thing.ts')).toBeVisible();
    });

    test('back to the backlog returns to the picker', async ({ page }) => {
        await row(page, 'Fix the thing').click();
        await expect(page.getByRole('tablist')).toBeVisible();
        await page.getByRole('button', { name: '← backlog' }).click();
        await expect(page.getByRole('tablist')).toHaveCount(0);
        await expect(page.getByText('PT-PT audio labels')).toBeVisible();
    });

    test('a ticket driven only in ANOTHER repo reads as not-driven here (no phantom run)', async ({
        page,
    }) => {
        // #9 has a resolve run - but for a DIFFERENT repo. The strip must not borrow it: this
        // repo never drove #9, so its backlog row shows no 'stalled' flag...
        await expect(
            row(page, 'Never driven here').getByText('stalled', { exact: true }),
        ).toHaveCount(0);
        // ...and opening it offers a first Resolve, never a Re-drive of a run that was never ours.
        await row(page, 'Never driven here').click();
        await expect(page.getByRole('button', { name: /Resolve #9 · gated/ })).toBeVisible();
        await expect(page.getByRole('button', { name: /Re-drive #9/ })).toHaveCount(0);
    });

    test('a FAIL verdict offers Review alongside Re-drive, not a dead end', async ({ page }) => {
        await row(page, 'Broken thing').click();
        // The Review stop reads FAIL...
        await expect(stop(page, 'Review').first().getByText('FAIL', { exact: true })).toBeVisible();
        // ...and BOTH acts are offered: re-drive the resolve (the findings are the work order)
        // AND drive a fresh Review to supersede the stale FAIL - the reported "can't trigger any
        // other verdict run" dead-end, fixed.
        await expect(page.getByRole('button', { name: /Re-drive #10 · gated/ })).toBeVisible();
        await expect(page.getByRole('button', { name: /Review #20 again/ })).toBeVisible();
    });

    test('a merge-ready ticket still offers an always-available re-drive escape hatch', async ({
        page,
    }) => {
        // #7 sits at Merge (PASS + green): the primary is Merge #14. But a resolution you dislike
        // must never dead-end at "merge or nothing" - the pre-cockpit acts rail always let you run
        // another resolve. The escape hatch restores it alongside the Merge primary.
        await row(page, 'Fix the thing').click();
        await expect(page.getByRole('button', { name: /Merge #14/ })).toBeVisible();
        await expect(page.getByText('Not what you wanted? Run another resolve')).toBeVisible();
        await expect(page.getByRole('button', { name: /Re-drive #7 · gated/ })).toBeVisible();
    });

    test('an awaiting-verdict ticket offers the re-drive escape hatch, not only Review', async ({
        page,
    }) => {
        // #11's PR #21 is open with an 'awaiting' verdict (nextAct = review). The reported case:
        // a verdict stuck awaiting (or a review you don't want to wait on) left ONLY the Review
        // button, no way back to the worker. Now Review AND a re-drive are both offered.
        await row(page, 'One-shot in flight').click();
        await expect(page.getByRole('button', { name: /Review #21/ })).toBeVisible();
        await expect(page.getByText('Not what you wanted? Run another resolve')).toBeVisible();
        await expect(page.getByRole('button', { name: /Re-drive #11 · gated/ })).toBeVisible();
    });

    intent(
        'INT-FC-R66',
        'an UNRECORDED verdict reads as its own state on the line and an amber pill, and never merges',
        async ({ page }) => {
            await row(page, 'Self-reviewed thing').click();
            // The Review stop names the state and what it needs: an independent reviewer.
            const review = stop(page, 'Review').first();
            await expect(review.getByText('unrecorded', { exact: true })).toBeVisible();
            await expect(review).toHaveAttribute('title', /awaits an independent reviewer/);
            await expect(review.getByText('awaiting', { exact: true })).toHaveCount(0);
            await review.click();
            await expect(
                page.getByText(/its review is UNRECORDED .* awaits an independent reviewer/),
            ).toBeVisible();
            // The pill says unrecorded, in the fail-closed amber, and its title says why.
            const pill = page.getByTitle(/ending VERDICT: UNRECORDED/);
            await expect(pill).toHaveText('unrecorded');
            await expect(pill).toHaveClass(/text-amber-400/);
            await expect(pill).toHaveAttribute('title', /awaits an independent reviewer/);
            // Fail-closed: the Merge stop is blocked with the reason, the act is a Review, and
            // no Merge button is offered.
            await expect(
                stop(page, 'Merge').first().getByText('blocked', { exact: true }),
            ).toBeVisible();
            await expect(page.getByRole('button', { name: /Review #22/ })).toBeVisible();
            await expect(page.getByRole('button', { name: /Merge #22/ })).toHaveCount(0);
            await stop(page, 'Merge').first().click();
            await expect(
                page.getByText(
                    'Blocked: the review is UNRECORDED - the PR awaits an independent reviewer.',
                ),
            ).toBeVisible();
        },
    );

    // #11's PR carries 'awaiting'; #13's carries a verdict the console does not know, which
    // must fall to awaiting too, never widen into unrecorded.
    for (const [ticket, verdict] of [
        ['One-shot in flight', 'an awaiting'],
        ['Unknown verdict thing', 'an unknown'],
    ] as const) {
        intent(
            'INT-FC-R66',
            `${verdict} verdict reads awaiting, apart from UNRECORDED`,
            async ({ page }) => {
                await row(page, ticket).click();
                const review = stop(page, 'Review').first();
                await expect(review.getByText('awaiting', { exact: true })).toBeVisible();
                await expect(review).toHaveAttribute('title', /awaiting a fresh-eyes verdict/);
                await stop(page, 'Merge').first().click();
                const pill = page.getByTitle(/No fresh-eyes verdict yet/);
                await expect(pill).toHaveText('awaiting');
                await expect(page.getByTitle(/ending VERDICT: UNRECORDED/)).toHaveCount(0);
                await expect(
                    page.getByText('Blocked: no fresh-eyes PASS yet - nothing merges unreviewed.'),
                ).toBeVisible();
            },
        );
    }

    test('a merged ticket does NOT offer the re-drive escape hatch (Close is the only move)', async ({
        page,
    }) => {
        // Re-driving landed work was a real bug: once the PR merged, Close is the only act and the
        // escape hatch is withheld - never a way to reopen resolved-and-merged work.
        await row(page, 'Merged already').click();
        await expect(page.getByRole('button', { name: /Close #8/ })).toBeVisible();
        await expect(page.getByText('Not what you wanted? Run another resolve')).toHaveCount(0);
    });

    test('the Review stop surfaces the live review run with its controls', async ({ page }) => {
        // #7 has open PR #14 with a gated review run in flight. Open the ticket and its Review stop.
        await row(page, 'Fix the thing').click();
        await stop(page, 'Review').first().click();

        // The reported gap, closed: a driven Review is watchable HERE (labelled by its PR),
        // not vanished behind "no fresh-eyes review yet" while the worker runs.
        await expect(page.getByText('review #14', { exact: true })).toBeVisible();

        // ...and manageable like the delivery cockpit: Stop / Terminate are right here.
        await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Terminate', exact: true })).toBeVisible();

        // The live log tail opens on demand.
        await page.getByRole('button', { name: 'Logs', exact: true }).click();
        await expect(page.getByText('fresh-eyes worker booting…')).toBeVisible();

        // The PR diff and the posted review both live here now (PR + Verdict collapsed).
        await expect(page.getByText('src/thing.ts')).toBeVisible();
    });

    test("a one-shot drive's review is watchable at the Review stop, not just Resolve", async ({
        page,
    }) => {
        // #11 is driven one-shot: ONE resolve Workflow whose second step reviews PR #21. That
        // review must surface at the Review stop too, though it is a step of the resolve run.
        await row(page, 'One-shot in flight').click();
        await stop(page, 'Review').first().click();

        // The one-shot resolve run (its review step live) shows here, tagged one-shot, manageable.
        await expect(page.getByText('resolve #11', { exact: true })).toBeVisible();
        await expect(page.getByText('one-shot', { exact: true }).first()).toBeVisible();
        await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeVisible();
    });

    test('the Merge stop shows the engine judgement for a one-shot drive', async ({ page }) => {
        await row(page, 'One-shot in flight').click();
        await stop(page, 'Merge').first().click();

        // The engine's one-shot gate is visible at the Merge stop (not just a line in the Act
        // rail): it merges on a recorded PASS, re-drives on a FAIL, else parks for the operator.
        await expect(page.getByText('one-shot engine', { exact: true })).toBeVisible();
        await expect(page.getByText(/merges on a recorded VERDICT: PASS/)).toBeVisible();
    });

    test("a ticket's header shows Running only for ITS OWN run, not any repo run", async ({
        page,
    }) => {
        // The phantom the operator smelled: #11's one-shot resolve is live, so SOMETHING is
        // running in this repo. Opening #8 - which has no run of its own - must not borrow that
        // 'Running' into its header. The badge is scoped to the open ticket, not the repo.
        await row(page, 'Merged already').click();
        await expect(page.getByText('Running', { exact: true })).toHaveCount(0);
        // But #7, whose PR #14 has a live review run, DOES light up - it is genuinely in flight.
        await page.getByRole('button', { name: '← backlog' }).click();
        await row(page, 'Fix the thing').click();
        await expect(page.getByText('Running', { exact: true }).first()).toBeVisible();
    });

    test('the backlog flags a ticket whose resolve is in flight as running', async ({ page }) => {
        // #11's one-shot resolve run is live -> its backlog row shows a 'running' flag, so the
        // operator watches it rather than re-driving (the Fleet Inbox's signal, in the picker).
        await expect(
            row(page, 'One-shot in flight').getByText('running', { exact: true }),
        ).toBeVisible();
        // #7's live run is a REVIEW, not a resolve, so its row stays 'at merge' - the merge-ready
        // state stays legible even while the PR is being re-reviewed.
        await expect(row(page, 'Fix the thing').getByText('at merge', { exact: true })).toBeVisible();
    });

    test('the PR file changes open a functional local diff with CDN blocked', async ({ page, baseURL }, testInfo) => {
        test.setTimeout(60_000);
        const network = await localEditorNetwork(page, baseURL!);
        await row(page, 'Fix the thing').click();
        await stop(page, 'Review').first().click();
        // The changed file's diff is folded on arrival - a compact summary row, uniformly,
        // regardless of how many files the PR touches.
        const file = page.locator('details').filter({ hasText: 'src/thing.ts' });
        await expect(file).toHaveJSProperty('open', false);
        // Clicking the summary expands it.
        await file.getByText('src/thing.ts').click();
        await expect(file).toHaveJSProperty('open', true);
        await expect(file.locator('.monaco-diff-editor')).toBeVisible({ timeout: 20_000 });
        await expect(file.locator('.view-lines').filter({ hasText: 'new' }).first()).toBeVisible();
        await expect(file.locator('.view-lines').filter({ hasText: 'old' }).first()).toBeVisible();
        await expect(file.locator('.line-insert').first()).toBeVisible({ timeout: 20_000 });
        await expect(file.locator('.line-delete').first()).toBeVisible();
        await expect.poll(() => network.workers, { timeout: 10_000 }).toContainEqual(expect.stringMatching(/editor\.worker/));
        await expect.poll(() => network.responses.some(({ url, status }) => /editor\.worker/.test(url) && status === 200)).toBe(true);
        expect(network.external).toEqual([]);
        expect(network.errors).toEqual([]);
        expect(network.responses.every(({ status }) => status === 200)).toBe(true);
        const sanitizers = await network.checkSanitizer();
        await testInfo.attach('local-diff-network', { body: JSON.stringify({ ...network, sanitizers }, null, 2), contentType: 'application/json' });
        await testInfo.attach('local-pr-diff', { body: await page.screenshot(), contentType: 'image/png' });
    });

    test('the posted review is expanded by default (the diff folds, the verdict reads)', async ({
        page,
    }) => {
        await row(page, 'Fix the thing').click();
        await stop(page, 'Review').first().click();
        // The review's body is the substance you came to read - it shows without a click, even
        // as the bulky file diffs stay folded above it.
        await expect(page.getByText('looks good')).toBeVisible();
    });

    test('the live run surface is a toggle: clicking the selected run row hides it', async ({
        page,
    }) => {
        await row(page, 'Fix the thing').click();
        await stop(page, 'Review').first().click();
        // The newest run is selected by default, so its Argo surface (Stop / Terminate) shows.
        await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeVisible();
        // Clicking the already-selected run row collapses the surface...
        await page.getByRole('button').filter({ hasText: 'review #14' }).click();
        await expect(page.getByRole('button', { name: 'Stop', exact: true })).toHaveCount(0);
        // ...and clicking it again brings it back.
        await page.getByRole('button').filter({ hasText: 'review #14' }).click();
        await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeVisible();
    });
});

// The one-shot ledger panel in the Act rail. It is the operator's whole view of what the engine
// did while nobody watched, so it must say what the engine is actually doing per row - and it
// must stay a panel, never crowding the co-pilot out of the rail it shares.
test.describe('the one-shot drives panel', () => {
    // A busy repo: one row the engine has said nothing about yet, one it is waiting on CI for,
    // one it re-drove, one settled outcome - plus enough more to overflow the panel's height.
    const DRIVEN = [
        { handle: 'h-inflight', repo: 'example-org/acme-widget', ticket: 11, acted: false, result: '' },
        {
            handle: 'h-checks',
            repo: 'example-org/acme-widget',
            ticket: 10,
            acted: false,
            result: 'PR #20 open - the merge gate waits on its checks',
        },
        {
            handle: 'h-redrive',
            repo: 'example-org/acme-widget',
            ticket: 7,
            acted: false,
            result: "attempt 2/2: re-driving resolve on the review's findings",
        },
        {
            handle: 'h-merged',
            repo: 'example-org/acme-widget',
            ticket: 8,
            acted: true,
            result: 'merged PR #16 on the recorded PASS',
        },
        ...Array.from({ length: 8 }, (_, i) => ({
            handle: `h-more-${i}`,
            repo: 'example-org/acme-widget',
            ticket: 100 + i,
            acted: true,
            result: `parked: PR #${200 + i} verdict awaiting, checks unknown`,
        })),
    ];

    test.beforeEach(async ({ page }) => {
        await stubApi(page);
        await page.route('**/api/maintenance/state?*', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(contractFixture({ ...MAINT_STATE, driven: DRIVEN }, RUNS)),
            }),
        );
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=maintenance');
        await row(page, 'One-shot in flight').click();
    });

    test('each row reads the engine own word for the state it is in', async ({ page }) => {
        // A drive the engine has said nothing about yet is the ONLY one that reads as a run in
        // flight. A finished run waiting on CI, and a re-drive on the reviewer's findings, each
        // say so - reading them as "running" hid a drive whose PR had been open for days.
        await expect(page.getByText(/the merge gate waits on its checks/)).toBeVisible();
        await expect(page.getByText(/re-driving resolve on the review/)).toBeVisible();
        await expect(page.getByText(/merged PR #16 on the recorded PASS/)).toBeVisible();
        await expect(page.getByText(/the engine reads the verdict from GitHub/)).toHaveCount(1);
    });

    test('a long ledger scrolls inside the panel and leaves the co-pilot its room', async ({
        page,
    }) => {
        // The panel shares the Act rail with the co-pilot. However many drives it carries, the
        // composer stays reachable: the list scrolls in place rather than growing the column.
        const composer = page.getByPlaceholder('Ask the co-pilot…');
        await expect(composer).toBeInViewport();
        const list = page.locator('div.overflow-y-auto').filter({ hasText: 'merged PR #16' });
        expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    });
});

// The maintenance state read is slow (it fans out to GitHub). While it is in flight the pane
// must show its shape - a skeleton, not a blank wait and not a false "no tickets" - and it must
// never leave the PREVIOUS project's tickets on screen under the new one. This block stubs a
// deliberately delayed state so that loading window is observable.
test.describe('maintenance pane loading', () => {
    test('a slow state read shows a loading skeleton, then the backlog', async ({ page }) => {
        await stubApi(page);
        // The delayed state read (added after stubApi, so it wins for this path).
        await page.route('**/api/maintenance/state?*', async (route) => {
            await new Promise((r) => setTimeout(r, 700));
            return route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(contractFixture(MAINT_STATE, RUNS)),
            });
        });
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto('/d?repo=example-org%2Facme-widget&mode=maintenance');
        // Substance during the wait: the skeleton holds the pane's shape...
        await expect(page.getByRole('status', { name: /loading tickets/i })).toBeVisible();
        // ...and it is NOT the false "no tickets" empty state (the bug where an empty backlog
        // showed mid-fetch).
        await expect(page.getByText(/No open tickets/)).toHaveCount(0);
        // Then the real backlog arrives and the skeleton clears.
        await expect(page.getByText('PT-PT audio labels')).toBeVisible();
        await expect(page.getByRole('status', { name: /loading tickets/i })).toHaveCount(0);
    });
});


test('a fresh maintenance receipt cannot select a same-number run in another repository', async ({ page }) => {
    await stubApi(page);
    await page.route('**/api/maintenance/state*', async (route) => {
        const repo = new URL(route.request().url()).searchParams.get('repo');
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture({ ...MAINT_STATE, repo }, RUNS)) });
    });
    const compiled = JSON.parse(execFileSync(process.env.PYTHON ?? 'python', [
        path.resolve('e2e/compiled_runs_fixture.py'), OVERVIEW.repo, 'm-fresh', 'Running', 'maintenance', 'resolve', '7', 'gated',
    ], { encoding: 'utf8' }));
    await page.route('**/api/maintenance/drive', async (route) => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ run_id: compiled.run_id, handle: compiled.handle }) });
    });
    await page.goto('/d?repo=example-org%2Facme-widget&mode=maintenance');
    await row(page, 'Fix the thing').click();
    await page.getByRole('button', { name: /Re-drive #7 · gated/ }).click();
    await page.evaluate(() => {
        history.pushState({}, '', '/d?repo=other-org%2Facme-widget&mode=maintenance');
        dispatchEvent(new PopStateEvent('popstate'));
    });
    await row(page, 'Fix the thing').click();
    await stop(page, 'Resolve').click();
    await expect(page.getByText('No resolve run yet.', { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Stop', exact: true })).toHaveCount(0);
});
