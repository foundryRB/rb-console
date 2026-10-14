import { contractFixture } from './contract-fixture';
import { test, expect, type Page } from '@playwright/test';

// The Close-line act is the console's ONLY way to end a delivery, so INT-FC-R79 makes it
// unconditional: one dedicated slot on the line card, occupied in every derived status and
// under every run state. It used to be conditional twice over - the primary button took it
// on a learned line, and the slot beside the primary held a Learn re-drive instead - so a
// learned line whose run was failed, running, or parked at a gate gave the primary to the
// run and the slot to the re-drive, and the close rendered NOWHERE (alexandria-main: status
// learned, Build+Ship failed x4). This suite is the machine gate on that: the button is
// present, exactly once, across the cross-product of status and run state.
//
// Its fixtures ARE a learned line, so the second read the cockpit owes that line rides here
// too: the phase strip must say Learn is done (INT-FC-R106's stamp), not "current".

const PHASES = ['scope', 'design', 'intent+plan', 'build+ship', 'learn'].map((name, i) => ({
    name,
    question: `Q${i}`,
    skill: 'some-skill',
    studio: null,
    gate: name === 'learn' ? null : ['proposal', 'design', 'plan', 'delivery'][i],
    gate_signed_on: name === 'learn' ? null : '2026-07-23',
    record: name === 'learn' ? null : `${name}.md`,
    record_present: name !== 'learn',
    is_current: name === 'learn',
    needs_review: false,
    artifact: null,
}));

const overview = (status: string, learnedOn: string | null) => ({
    repo: 'example-org/acme-widget',
    exists: true,
    status,
    phase: 'learn',
    next_skill: null,
    next_command: null,
    blocked_gate: status === 'awaiting-gate' ? 'delivery' : null,
    gates: [],
    records_present: ['scope.md', 'design.md', 'handoff.md', 'build.md'],
    learned_on: learnedOn,
    config: {
        mode: 'interactive',
        provider: 'claude',
        base_url: '',
        model: 'sonnet',
        agent: 'my-claude',
        timeout_hours: 1,
        credentialed: true,
    },
    phases: PHASES,
});

// The executor phases the run band can be in. `null` is a line with no run at all.
type RunPhase = 'Failed' | 'Running' | 'Suspended' | 'Succeeded' | null;

const RUN = (phase: string) => ({
    kind: 'delivery',
    repo: 'example-org/acme-widget',
    handle: 'live:argo/delivery-acme-widget-qk7g1',
    name: 'delivery-acme-widget-qk7g1',
    run_id: 'qk7g1',
    mode: 'interactive',
    phase,
    created: '2026-07-24T18:57:00Z',
    started: '2026-07-24T18:57:00Z',
    finished: null,
    progress: '0/4',
});

/** A worker pod in the run graph, so a phase node can be upgraded by live executor state.
 * The suite's default graph is node-less: most cases care about the derived read alone. */
const POD = (phase: string, live: string) => ({
    name: `delivery-acme-widget-qk7g1-worker-${phase}`,
    type: 'Pod',
    template: `worker-${phase}`,
    phase: live,
    startedAt: '2026-07-24T18:57:00Z',
    message: null,
});

async function stubApi(
    page: Page,
    status: string,
    runPhase: RunPhase,
    learnedOn: string | null = null,
    graphNodes: unknown[] = [],
) {
    await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname.replace(/^\/api/, '');
        const body = (data: unknown) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(contractFixture(data, runPhase ? [RUN(runPhase)] : [], { [RUN(runPhase ?? "Succeeded").handle]: { nodes: graphNodes } })) });
        switch (path) {
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(overview(status, learnedOn));
            case '/deliveries/config':
                return body(overview(status, learnedOn).config);
            case '/runs':
                return body({ runs: runPhase ? [RUN(runPhase)] : [] });
            case '/runs/graph':
                return body({ name: 'delivery-acme-widget-qk7g1', phase: runPhase ?? 'Succeeded', nodes: graphNodes });
            case '/fleet':
                return body({ projects: [] });
            case '/studios':
                return body({ studios: [] });
            case '/agents':
                return body({ agents: [] });
            default:
                return body({});
        }
    });
}

const closeBtn = (page: Page) => page.getByRole('button', { name: /Close line/ });

async function openCockpit(
    page: Page,
    status: string,
    runPhase: RunPhase,
    learnedOn: string | null = null,
    graphNodes: unknown[] = [],
) {
    await stubApi(page, status, runPhase, learnedOn, graphNodes);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/d?repo=example-org%2Facme-widget');
    // The line card has rendered (its primary is always there) before anything is asserted.
    await expect(page.getByRole('button', { name: /Plan · dry run/ })).toBeVisible();
}

// status x run state. Every cell must show exactly one Close line button.
const CASES: { status: string; runPhase: RunPhase; learnedOn: string | null; label: string }[] = [
    { status: 'learned', runPhase: 'Failed', learnedOn: '2026-07-24', label: 'learned + a failed run (the reported hole)' },
    { status: 'learned', runPhase: 'Running', learnedOn: '2026-07-24', label: 'learned + a live run' },
    { status: 'learned', runPhase: 'Suspended', learnedOn: '2026-07-24', label: 'learned + a run parked at a gate' },
    { status: 'learned', runPhase: null, learnedOn: '2026-07-24', label: 'learned with no run' },
    { status: 'learned', runPhase: 'Succeeded', learnedOn: '2026-07-24', label: 'learned after a clean run' },
    { status: 'delivered', runPhase: 'Failed', learnedOn: null, label: 'delivered + a failed run' },
    { status: 'delivered', runPhase: null, learnedOn: null, label: 'delivered with no run' },
    { status: 'run-phase', runPhase: 'Running', learnedOn: null, label: 'mid-line with a live run' },
    { status: 'awaiting-gate', runPhase: 'Suspended', learnedOn: null, label: 'parked awaiting a gate signature' },
    { status: 'degraded', runPhase: 'Failed', learnedOn: null, label: 'degraded after an aborted phase' },
];

test.describe('the Close-line act is unconditional (INT-FC-R79)', () => {
    for (const { status, runPhase, learnedOn, label } of CASES) {
        test(`it is reachable on a line that is ${label}`, async ({ page }) => {
            await openCockpit(page, status, runPhase, learnedOn);
            // Present, and exactly once - it holds one slot, never doubling into the primary.
            await expect(closeBtn(page)).toHaveCount(1);
            await expect(closeBtn(page)).toBeVisible();
            await expect(closeBtn(page)).toBeEnabled();
        });
    }

    test('the primary keeps naming the run act, and never becomes the close', async ({ page }) => {
        // The reported line: learned, with Build+Ship failed x4. The run's own act stays the
        // primary (a failed run wants re-driving), and the close sits beside it - both reachable.
        await openCockpit(page, 'learned', 'Failed', '2026-07-24');
        await expect(page.getByRole('button', { name: /↻ Re-drive$/ })).toBeVisible();
        await expect(closeBtn(page)).toBeVisible();
    });

    test('a learned line names its Learn re-drive honestly instead of offering a plain Drive', async ({ page }) => {
        // No run in flight, so the primary is the phase act: Learn demonstrably ran, so the
        // verb is a re-drive (an idempotent no-op), not a Drive that implies unfinished work.
        await openCockpit(page, 'learned', null, '2026-07-24');
        const row = page.getByRole('button', { name: /Plan · dry run/ }).locator('xpath=..');
        await expect(row.getByRole('button', { name: /↻ Re-drive Learn/ })).toBeVisible();
        // Nowhere on a learned line - the phase pane below carries its own copy of this verb,
        // and it read "Drive Learn" while the control row above it read "Re-drive Learn".
        await expect(page.getByRole('button', { name: /▶ Drive/ })).toHaveCount(0);
    });

    // R79 kept the close in a slot no run state can evict, and pointed a finished line at it
    // with a red BORDER - beside a filled primary, which reads as the main act whatever it
    // says. So a done-and-learned line still shouted "Re-drive Learn" (reported). The fill is
    // the pointer now. Asserted on computed background rather than class names: "which control
    // is filled" is the actual claim, and it survives a restyle that renames the utilities.
    // Polled, not sampled once (issue #38): `closeIsNext` is derived from async state, so
    // before it settles the button still renders its DEFAULT variant - which is filled. A
    // single `expect(await ...)` read awaits the value and then asserts a dead boolean, with
    // none of the auto-retry Playwright's own matchers have, so on a contended runner it
    // caught the pre-settle frame and reported the close as filled. Only the sampling
    // changes; the claim is still computed background, so a restyle that renames the
    // utilities cannot make it pass vacuously.
    const expectFilled = (page: Page, name: RegExp, isFilled: boolean) =>
        expect
            .poll(() =>
                page
                    .getByRole('button', { name })
                    .evaluate(
                        (el) => window.getComputedStyle(el).backgroundColor !== 'rgba(0, 0, 0, 0)',
                    ),
            )
            .toBe(isFilled);

    test('a finished line puts the fill on the close, and drops the Learn re-drive to an outline', async ({ page }) => {
        // The reported cockpit exactly: learned, its last run Succeeded, nothing in flight.
        await openCockpit(page, 'learned', 'Succeeded', '2026-07-24');
        await expectFilled(page, /Close line/, true);
        await expectFilled(page, /↻ Re-drive Learn/, false);
    });

    test('a run that wants attention keeps the fill on its own act, not on the close', async ({ page }) => {
        // The inverse, so the flip above cannot pass by being unconditional: a failed run is
        // the more urgent act AND the state whose primary the close must never become, so the
        // emphasis stays put. The close is still there, still red - just not the loud one.
        await openCockpit(page, 'learned', 'Failed', '2026-07-24');
        await expectFilled(page, /↻ Re-drive$/, true);
        await expectFilled(page, /Close line/, false);
    });

    test('pressing it confirms first, then posts the close for this delivery', async ({ page }) => {
        await openCockpit(page, 'learned', 'Failed', '2026-07-24');
        const posted: unknown[] = [];
        await page.route('**/api/deliveries/close', async (route) => {
            posted.push(route.request().postDataJSON());
            return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
        });
        // The act ends the line (tag, then remove the scratch ref), so it is confirmed -
        // dismissing must post nothing.
        page.once('dialog', (d) => void d.dismiss());
        await closeBtn(page).click();
        expect(posted).toHaveLength(0);
        page.once('dialog', (d) => void d.accept());
        await closeBtn(page).click();
        await expect.poll(() => posted).toEqual([{ target: 'example-org/acme-widget' }]);
    });
});

test.describe('the line strip reads a learned Learn as done (INT-FC-R106)', () => {
    // Learn leaves no record, so record_present is permanently false for it and the node
    // could only ever fall through to is_current - which the resolver pins at learn forever
    // past the stamp. The strip therefore said "current" on a line the masthead was badging
    // LEARNED and whose primary already said Re-drive: the same "did Learn run?" confusion
    // R106 was written to kill, surviving in the one component the stamp never reached.
    const learnStamp = (page: Page) => page.getByText('done · learned 2026-07-24');
    // A phase sub-label is the only element on the page whose whole text is "current".
    const currentLabel = (page: Page) => page.getByText('current', { exact: true });

    test('the learn node carries the stamp and its date, not "current"', async ({ page }) => {
        await openCockpit(page, 'learned', null, '2026-07-24');
        await expect(learnStamp(page)).toBeVisible();
        await expect(currentLabel(page)).toHaveCount(0);
    });

    test('an un-run Learn still reads current - the stamp is what changes it', async ({ page }) => {
        // The inverse case, so the assertion above cannot pass by the label being gone.
        await openCockpit(page, 'delivered', null, null);
        await expect(currentLabel(page)).toBeVisible();
        await expect(learnStamp(page)).toHaveCount(0);
        // ...and the phase pane's verb reads off the same fact: no stamp, so Learn is a Drive.
        await expect(page.getByRole('button', { name: /▶ Drive Learn/ })).toBeVisible();
    });

    test('a live re-drive of a learned Learn outranks the stamp', async ({ page }) => {
        // The strip's precedence is unchanged: the executor's live state always wins over
        // the derived read, so an in-flight re-drive shows as running, not as done.
        await openCockpit(page, 'learned', 'Running', '2026-07-24', [POD('learn', 'Running')]);
        await expect(page.getByText('running', { exact: true })).toBeVisible();
        await expect(learnStamp(page)).toHaveCount(0);
    });
});


test('an unknown command retains its operation ID and inspects the persisted receipt', async ({ page }) => {
    await openCockpit(page, 'learned', null, '2026-07-24');
    const ids: string[] = [];
    await page.route('**/api/deliveries/close', async (route) => {
        ids.push(route.request().headers()['idempotency-key']);
        await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
            code: 'operation_unknown', message: 'Outcome unknown', detail: 'Dispatch has no authoritative outcome', operation_key: 'receipt-key',
        }) });
    });
    await page.route('**/api/operations/receipt-key', async (route) => route.fulfill({
        contentType: 'application/json', body: JSON.stringify({ operation_key: 'receipt-key', state: 'unknown', reason: 'Awaiting authoritative resolution', evidence: { repository: 'example-org/acme-widget' } }),
    }));
    page.on('dialog', (dialog) => dialog.accept());
    await closeBtn(page).click();
    // INT-FC-R190: the message names the key the operations endpoint inspects.
    await expect(page.getByText(/Outcome unknown\. Operation receipt-key/).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Inspect receipt' })).toBeVisible();
    await page.getByRole('button', { name: 'Inspect receipt' }).click();
    await expect(page.getByText(/Persisted receipt: unknown/)).toBeVisible();
    await expect(page.getByText(/Awaiting authoritative resolution/)).toBeVisible();
    await closeBtn(page).click();
    await expect.poll(() => ids.length).toBe(2);
    expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(ids[1]).toBe(ids[0]);
});


test('claim statements retain their full multiline text and wrap on a narrow screen', async ({ page }) => {
    await stubApi(page, 'run-phase', null);
    const statement = 'A full statement remains visible even when it contains a long explanation that wraps across multiple lines on a narrow screen.\nA second line must preserve its authored wording and remain readable.';
    const data = { ...overview('run-phase', null), phase: 'intent+plan', phases: PHASES.map((phase) => ({ ...phase, is_current: phase.name === 'intent+plan' })) };
    await page.route('**/api/deliveries/overview?*', async (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(contractFixture(data)) }));
    await page.route('**/api/deliveries/substance?*', async (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ claims: [{ id: 'INT-TEST-001', statement, status: 'active', criticality: 'high' }] }) }));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/d?repo=example-org%2Facme-widget');
    await page.getByRole('button', { name: 'Load phase content', exact: true }).click();
    const claim = page.getByText(statement);
    await expect(claim).toBeVisible();
    const layout = await claim.evaluate((element) => ({ whiteSpace: getComputedStyle(element).whiteSpace, height: element.getBoundingClientRect().height, lineHeight: parseFloat(getComputedStyle(element).lineHeight) }));
    expect(layout.whiteSpace).toBe('pre-wrap');
    expect(layout.height).toBeGreaterThan(layout.lineHeight * 2);
});

test('a truncated successful command receipt stays unknown and retries the same operation', async ({
    page,
}) => {
    await openCockpit(page, 'learned', null, '2026-07-24');
    const keys: string[] = [];
    await page.route('**/api/deliveries/close', async (route) => {
        keys.push(route.request().headers()['idempotency-key']);
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{"closed":' });
    });
    page.on('dialog', (dialog) => void dialog.accept());
    await closeBtn(page).click();
    await expect(page.getByText(/Outcome unknown\. Operation/).first()).toBeVisible();
    await expect(closeBtn(page)).toBeEnabled();
    await closeBtn(page).click();
    await expect.poll(() => keys.length).toBe(2);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    await expect(page.getByText(/Outcome unknown\. Operation/).first()).toBeVisible();
});

test('a command the source could not admit reads as not done, and a retry is a new operation', async ({
    page,
}) => {
    await openCockpit(page, 'learned', null, '2026-07-24');
    const keys: string[] = [];
    await page.route('**/api/deliveries/close', async (route) => {
        keys.push(route.request().headers()['idempotency-key']);
        await route.fulfill({ status: 503, contentType: 'application/json', headers: { 'Retry-After': '30' }, body: JSON.stringify({
            code: 'source_unavailable', message: 'The source is unavailable. Its last observation may be stale.', detail: 'The source is unavailable. Its last observation may be stale.',
        }) });
    });
    page.on('dialog', (dialog) => void dialog.accept());
    await closeBtn(page).click();
    await expect(page.getByText(/The source is unavailable/).first()).toBeVisible();
    await expect(page.getByText(/Outcome unknown/)).toHaveCount(0);
    await expect(closeBtn(page)).toBeEnabled();
    await closeBtn(page).click();
    await expect.poll(() => keys.length).toBe(2);
    expect(keys[1]).not.toBe(keys[0]);
});
