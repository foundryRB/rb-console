import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { test, expect, type Page } from '@playwright/test';
import { contractFixture } from './contract-fixture';

// The light-mode contrast guard. The panes once painted their recessed surfaces with a black
// wash (bg-black/N) and de-emphasised text at 60% alpha: fine on the dark stage, a flat grey
// with unreadable text on the light one. The fix replaced them with theme-aware tokens
// (bg-well/N, text-faint, bg-editor) and measured every visible text node against its
// composited background. This spec keeps both halves true: the source carries no dark-only
// wash, and every page still clears WCAG 4.5:1 (3:1 for large text) in light mode. Dark mode
// joins once its own faint text is raised above 4.5:1.
//
// What the contrast check sees is what the fixtures render at rest: the fleet, the scope pane
// and its seven tabs, a record-only design, intent+plan claims, a build+ship worktree, the
// maintenance backlog, the promotion queue, settings and studios, at desktop width and the
// scope pane at phone width. Not rendered, so not measured: the 40% wells (the run band's
// step logs, the run-log and maintenance log viewers, the slug chip), the ticket line and its
// current step, the degraded panel and the redrive composer, the promotion and add-model
// forms, and the learn phase. The background is composited from ancestors' background-color
// only; gradients, glass blur and ancestor opacity are not modelled, which measured within
// 0.3 of the painted pixels on these views.

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src');

// A `dark:` variant is dark-only by construction, so it is the one prefix these may carry.
const FORBIDDEN: { pattern: RegExp; why: string }[] = [
    { pattern: /(?<!dark:)\bbg-black\/\d+/, why: 'a black wash is dark-only; use bg-well/N' },
    {
        pattern: /(?<!dark:)\btext-muted-foreground\/60\b/,
        why: 'a 60% muted foreground is dark-only; use text-faint',
    },
    {
        pattern: /(?<!dark:)\bbg-\[#[0-9a-fA-F]{3,8}\]/,
        why: 'a hard-coded surface cannot follow the theme; use a token',
    },
];

const walk = (dir: string): string[] =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const full = path.join(dir, entry.name);
        return entry.isDirectory() ? walk(full) : [full];
    });

test('the source carries no dark-only surface or text wash', () => {
    const hits: string[] = [];
    for (const file of walk(SRC).filter((f) => /\.tsx?$/.test(f))) {
        fs.readFileSync(file, 'utf8')
            .split('\n')
            .forEach((line, i) => {
                for (const { pattern, why } of FORBIDDEN) {
                    const m = pattern.exec(line);
                    if (m) {
                        hits.push(
                            `${path.relative(SRC, file)}:${i + 1}: ${m[0]} in "…${line.slice(Math.max(0, m.index - 30), m.index + m[0].length + 30).trim()}…" (${why})`,
                        );
                    }
                }
            });
    }
    expect(hits, hits.join('\n')).toEqual([]);
});

// Deterministic fixtures for the stubbed /api layer, neutral names throughout. Each repo
// parks the line at a different phase so every pane renders: scope with live substance,
// design with a record only, intent+plan with claims, build+ship with a worktree.
const REPOS = {
    scope: 'example-org/acme-widget',
    design: 'example-org/bar-svc',
    plan: 'example-org/qux-api',
    build: 'example-org/baz-app',
};

const project = (repo: string, extra: Record<string, unknown>) => ({
    repo,
    name: repo.split('/')[1],
    is_delivery: true,
    delivery_status: 'awaiting-gate',
    delivery_phase: 'scope',
    onboarded: false,
    live: null,
    updated: '2026-07-10T09:00:00Z',
    estimatekit: true,
    protopane: false,
    hidden: false,
    role: null,
    activity: 'suspended',
    app_name: '',
    host: '',
    ...extra,
});

const FLEET = [
    project(REPOS.scope, {}),
    project(REPOS.design, { delivery_phase: 'design', protopane: true }),
    project(REPOS.plan, {
        delivery_phase: 'intent+plan',
        delivery_status: 'in-progress',
        activity: 'running',
    }),
    project(REPOS.build, {
        delivery_phase: 'build+ship',
        onboarded: true,
        live: 'running',
        app_name: 'baz-app',
        host: 'baz-app.example.test',
        role: 'output',
    }),
    project('example-org/platform', {
        is_delivery: false,
        delivery_status: null,
        delivery_phase: null,
        estimatekit: false,
        activity: null,
        role: 'core',
        live: 'paused',
        onboarded: true,
    }),
];

const STUDIOS = [
    {
        studio: 'estimatekit',
        reachable: true,
        detail: 'reachable',
        url: 'https://estimatekit.example.test',
    },
    {
        studio: 'protopane',
        reachable: true,
        detail: 'reachable',
        url: 'https://protopane.example.test',
    },
    {
        studio: 'platform-studio',
        reachable: false,
        detail: 'unreachable',
        url: 'https://platform-studio.example.test',
    },
    {
        studio: 'playbook-studio',
        reachable: true,
        detail: 'reachable',
        url: 'https://playbook-studio.example.test',
    },
];

const INBOX = [
    {
        repo: 'example-org/plans',
        signal: 'red-ci',
        detail: 'default branch is red at 1.5.1: what merged is not shipping',
        act: 'investigate',
        number: null,
        ts: '',
        hidden: false,
        stage: '',
    },
    {
        repo: REPOS.build,
        signal: 'issue',
        detail: "#2 learn: 11 open Dependabot alerts left standing at the line's close",
        act: 'resolve',
        number: 2,
        ts: '2026-07-09T19:15:02Z',
        hidden: false,
        stage: 'open',
    },
    {
        repo: REPOS.build,
        signal: 'issue',
        detail: '#3 learn: the vendored font subset\'s name table reads "Regular"',
        act: 'resolve',
        number: 3,
        ts: '2026-07-09T19:15:04Z',
        hidden: false,
        stage: 'at-review',
    },
    {
        repo: REPOS.build,
        signal: 'pr',
        detail: '#5 fix(#3): rename the vendored font subset',
        act: 'review',
        number: 5,
        ts: '2026-07-10T08:00:00Z',
        hidden: false,
        stage: 'open',
    },
];

const AGENTS = [
    {
        name: 'house-claude',
        provider: 'claude',
        base_url: '',
        model: 'sonnet',
        models: ['sonnet', 'haiku'],
        configured: true,
    },
];

const RUNS = [
    {
        handle: 'live:workflow.argoproj.io/delivery-acme-widget-abc12',
        name: 'delivery-acme-widget-abc12',
        run_id: 'r-1',
        mode: 'interactive',
        maintenance: null,
        ticket: null,
        repo_slug: null,
        phase: 'Suspended',
        parked_gate: 'proposal',
        stop: null,
        created: '2026-07-10T07:21:59Z',
        started: '2026-07-10T07:21:59Z',
        finished: null,
        progress: '1/2',
        agents: ['architect', 'designer'],
    },
    {
        handle: 'live:workflow.argoproj.io/delivery-acme-widget-old99',
        name: 'delivery-acme-widget-old99',
        run_id: 'r-0',
        mode: 'interactive',
        maintenance: null,
        ticket: null,
        repo_slug: null,
        phase: 'Stopped',
        parked_gate: null,
        stop: 'superseded',
        created: '2026-07-09T14:05:50Z',
        started: '2026-07-09T14:05:50Z',
        finished: '2026-07-09T19:13:30Z',
        progress: '1/2',
        agents: ['architect'],
    },
];

const GRAPH = {
    name: 'delivery-acme-widget-abc12',
    phase: 'Suspended',
    stop: null,
    progress: '1/2',
    nodes: [
        {
            id: 'n0',
            name: 'delivery-acme-widget-abc12',
            type: 'Steps',
            agent: null,
            phase: 'Running',
            template: 'line',
            message: null,
            exitCode: null,
            children: ['n1'],
            startedAt: '2026-07-10T07:21:59Z',
            finishedAt: null,
            artifacts: [],
        },
        {
            id: 'n1',
            name: 'scope',
            type: 'Pod',
            agent: 'architect',
            phase: 'Succeeded',
            template: 'worker-scope',
            message: null,
            exitCode: '0',
            children: ['n2'],
            startedAt: '2026-07-10T07:21:59Z',
            finishedAt: '2026-07-10T07:34:17Z',
            artifacts: [],
        },
        {
            id: 'n2',
            name: 'gate-proposal',
            type: 'Suspend',
            agent: null,
            phase: 'Suspended',
            template: 'gate-proposal',
            message: null,
            exitCode: null,
            children: [],
            startedAt: '2026-07-10T07:34:27Z',
            finishedAt: null,
            artifacts: [],
        },
    ],
};

const PHASES = [
    {
        name: 'scope',
        question: 'What is asked, and what would it cost?',
        skill: 'deliver-engagement',
        studio: 'estimatekit',
        gate: 'proposal',
        record: 'proposal.md',
    },
    {
        name: 'design',
        question: 'What should it look and feel like?',
        skill: 'design-session',
        studio: 'protopane',
        gate: 'design',
        record: 'design.md',
    },
    {
        name: 'intent+plan',
        question: 'What must be true, and how do we build it?',
        skill: 'intent-session',
        studio: null,
        gate: 'plan',
        record: 'handoff.md',
    },
    {
        name: 'build+ship',
        question: 'Is it working software, and is it live?',
        skill: 'run-delivery-plan',
        studio: 'platform-studio',
        gate: 'delivery',
        record: 'build.md',
    },
    {
        name: 'learn',
        question: 'What did it teach, and what comes next?',
        skill: 'reconcile-delivery',
        studio: 'playbook-studio',
        gate: null,
        record: null,
    },
];

/** An overview parked at `current`: every earlier phase signed and recorded, the rest queued. */
const overview = (repo: string, current: string) => {
    const at = PHASES.findIndex((p) => p.name === current);
    return {
        repo,
        exists: true,
        status: 'awaiting-gate',
        phase: current,
        next_skill: null,
        next_command: `sign the ${PHASES[at].gate} gate`,
        blocked_gate: PHASES[at].gate,
        gates: PHASES.filter((p) => p.gate).map((p, i) => ({
            name: p.gate,
            signed_on: i < at ? '2026-07-08' : null,
        })),
        records_present: PHASES.slice(0, at + 1)
            .map((p) => p.record)
            .filter(Boolean),
        learned_on: null,
        seed: 'new',
        demo_of: '',
        config: {
            mode: 'interactive',
            provider: 'claude',
            base_url: '',
            model: 'sonnet',
            agent: 'house-claude',
            timeout_seconds: 21600,
            credentialed: true,
        },
        phases: PHASES.map((p, i) => ({
            ...p,
            gate_signed_on: i < at ? '2026-07-08' : null,
            record_present: i <= at && p.record !== null,
            is_current: i === at,
            needs_review: false,
            artifact:
                i <= at && p.studio
                    ? {
                          studio: p.studio,
                          reachable: true,
                          exists: true,
                          url: `https://${p.studio}.example.test/p/${repo.split('/')[1]}`,
                          detail: 'project',
                      }
                    : null,
        })),
    };
};

const SCOPE_SUBSTANCE = {
    summary: {
        name: 'Acme Widget',
        client: 'Example Health',
        description:
            "Employee-only widget service: installable web client, backoffice and API on the delivery platform, with sign-in on the app's realm.",
        phase_count: 1,
        requirement_count: 3,
        assumption_count: 2,
        archived: false,
    },
    audit: {
        passed: true,
        passed_count: 12,
        failed_count: 0,
        suggestions: [
            {
                title: 'Milestones clustered in one month',
                detail: 'Two milestones land in the same month; consider staggering them.',
                severity: 'warning',
                category: 'scheduling',
            },
        ],
    },
    estimate: { phases: [{ id: 'P1', effort_md: 42 }], total_md: 42 },
    requirements: [
        {
            id: 'AUTH-01',
            category: 'Authentication',
            description: 'Sign-in through the realm with OIDC',
            phases: ['P1'],
        },
        {
            id: 'AUTH-02',
            category: 'Authentication',
            description: 'Support MFA where the realm enforces it',
            phases: ['P1'],
        },
        {
            id: 'RPT-01',
            category: 'Reporting',
            description: 'A monthly usage report per site',
            phases: [],
        },
    ],
    phases: [
        {
            id: 'P1',
            phase: 'Phase 1',
            name: 'Acme Widget',
            description: 'Client, backoffice and API from design through pilot',
            requirement_ids: ['AUTH-01', 'AUTH-02'],
        },
    ],
    assumptions: [
        {
            id: 'ASM-001',
            group: 'Scope',
            title: 'Draft governs scope',
            assumption: 'The requirements draft is the build target; conflicts are priced.',
            confidence: 'HIGH',
            impact: 'HIGH',
            req_ids: ['ALL'],
        },
        {
            id: 'ASM-002',
            group: 'Scope',
            title: 'Load test in scope',
            assumption: 'A single pre-go-live load test is included.',
            confidence: 'MEDIUM',
            impact: 'CRITICAL',
            req_ids: ['RPT-01'],
        },
    ],
    activities: [
        {
            id: 'BLD-01',
            phase: 'P1',
            group: 'Design',
            activity: 'Architecture, data model, API contract',
            effort_md: 12,
            req_ids: ['AUTH-01', 'AUTH-02'],
            description: 'Hexagonal target architecture and the OpenAPI contract',
        },
        {
            id: 'BLD-02',
            phase: 'P1',
            group: 'Identity',
            activity: 'Realm, role model and sign-in flow',
            effort_md: 10,
            req_ids: ['AUTH-01'],
            description: 'OIDC clients, PKCE redirect, silent renewal',
        },
        {
            id: 'BLD-03',
            phase: 'P1',
            group: 'Reporting',
            activity: 'Usage report',
            effort_md: 20,
            req_ids: ['RPT-01'],
            description: 'Monthly aggregation per site with export',
        },
    ],
    architecture: {
        guidelines: [
            {
                id: 'GUIDE-001',
                group: 'Privacy',
                name: 'Minimum data',
                description: 'Only what the report needs is stored',
                rationale: 'Privacy by design',
            },
            {
                id: 'GUIDE-002',
                group: 'Security',
                name: 'Server-side authority',
                description: 'Every authorisation decision is enforced in the API',
                rationale: 'ASVS baseline',
            },
        ],
        components: [
            {
                phase: 'P1',
                layer: 'Client',
                component: 'Web Client',
                technology: 'React + TypeScript',
                description: 'Sign-in, profile, reports',
                scope: 'Full',
            },
            {
                phase: 'P1',
                layer: 'Backend',
                component: 'API Service',
                technology: 'Python FastAPI, hexagonal',
                description: 'Profiles, reports, administration',
                scope: 'Full',
            },
        ],
        diagrams: [
            {
                name: 'P1-overview',
                phase: 'P1',
                puml: '@startuml\n[Web Client] --> [API Service]\n@enduml\n',
                svg: '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="80"><rect x="8" y="8" width="224" height="64" fill="none" stroke="currentColor"/><text x="20" y="46" fill="currentColor">Web Client -> API Service</text></svg>',
            },
        ],
    },
};

const CLAIMS = [
    {
        id: 'INT-ACME-001',
        status: 'active',
        criticality: 'must',
        statement: "A signed-in employee sees only their own site's report",
    },
    {
        id: 'INT-ACME-002',
        status: 'draft',
        criticality: 'should',
        statement: 'The report exports as CSV within two seconds',
    },
    {
        id: 'INT-ACME-003',
        status: 'waived',
        criticality: 'could',
        statement: 'The client installs on a phone',
    },
];

const RECORD =
    '---\nphase: scope\nstatus: gate\ngate: proposal\nsigned: pending\nreviewed: 2026-07-10\n---\n\n# Proposal\n\nThe committed record of the phase. A record is not substance; the substance is the estimation project itself.\n\n## Requirements\n\n- AUTH-01 Sign-in through the realm\n- AUTH-02 MFA where enforced\n';

const TREE = [
    { path: '.github', type: 'tree', size: null },
    { path: '.github/workflows', type: 'tree', size: null },
    { path: '.github/workflows/build.yml', type: 'blob', size: 1339 },
    { path: 'README.md', type: 'blob', size: 3020 },
    { path: 'api', type: 'tree', size: null },
    { path: 'api/main.py', type: 'blob', size: 501 },
];

const pr = (number: number, title: string, extra: Record<string, unknown>) => ({
    number,
    title,
    author: 'maintainer',
    head: `fix/${number}`,
    head_sha: '',
    body: '',
    url: `https://github.com/${REPOS.build}/pull/${number}`,
    verdict: 'awaiting',
    checks: 'unknown',
    contributor: false,
    updated_at: '2026-07-09T11:15:36Z',
    state: 'merged',
    ...extra,
});

const MAINTENANCE = {
    repo: REPOS.build,
    positions: {
        repo: REPOS.build,
        issues: [
            {
                number: 8,
                title: 'The phone layout stops at 384 px and leaves white bands',
                author: 'maintainer',
                labels: ['bug'],
                url: `https://github.com/${REPOS.build}/issues/8`,
                created_at: '2026-07-10T13:08:44Z',
                complexity: 'M',
                priority: 'high',
                type: 'bug',
            },
            {
                number: 7,
                title: 'Render the static maps at 2x until the interactive map lands',
                author: 'maintainer',
                labels: ['enhancement'],
                url: `https://github.com/${REPOS.build}/issues/7`,
                created_at: '2026-07-10T06:15:01Z',
                complexity: 'S',
                priority: 'low',
                type: 'feature',
            },
            {
                number: 6,
                title: 'Complete the privacy notice',
                author: 'maintainer',
                labels: [],
                url: `https://github.com/${REPOS.build}/issues/6`,
                created_at: '2026-07-09T10:23:00Z',
                complexity: 'L',
                priority: 'lowest',
                type: 'task',
            },
        ],
        prs: [
            pr(5, 'fix(#3): rename the vendored font subset', {
                state: 'open',
                checks: 'green',
                head_sha: 'f7c0a0d',
                body: "Closes #3\n\nThe subset's name table now reads its weight.",
            }),
        ],
        train: {
            version: '1.11.2',
            unreleased_total: 1,
            breaking: 0,
            feat: 0,
            fix: 1,
            other: 0,
            next_version: '1.11.3',
            deployed: 'running',
            healthy: true,
            checks: 'green',
        },
        recent_closed: [
            pr(
                4,
                'fix(verification): remove the residue the deployed verification leaves behind',
                {},
            ),
        ],
    },
    action: {
        acts: ['resolve', 'review', 'reconcile-docs'],
        modes: ['gated', 'one-shot', 'direct'],
        default_mode: 'gated',
    },
    delivery: { status: 'awaiting-gate', phase: 'build+ship' },
    driven: [],
    home: null,
};

const PROMOTION = {
    repo: REPOS.build,
    declared: true,
    problem: '',
    proven: '1.11.2',
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
            accepted: '1.9.2',
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
            accepted: '1.8.0',
            door_ref: 'PR 14',
            detail: '',
            credential: 'partner-pair',
            door_shut: false,
        },
        {
            name: 'example-staging',
            kind: 'environment',
            destination: 'example / staging',
            door: 'commit',
            terms: 'version',
            acceptance: 'probe',
            state: 'unproven',
            accepted: '1.11.2',
            detail: 'serves 1.11.2, and its declared probe does not answer',
            door_ref: '',
            credential: '',
            door_shut: false,
        },
        {
            name: 'broken',
            kind: 'environment',
            destination: 'example / old',
            door: 'commit',
            terms: 'version',
            acceptance: 'probe',
            state: 'unreadable',
            accepted: '',
            detail: "the target's manifest could not be read",
            door_ref: '',
            credential: '',
            door_shut: true,
        },
    ],
};

/** Stub every /api call in-browser; the repo query picks which line answers. */
async function stubApi(page: Page) {
    await page.route('**/api/**', async (route) => {
        const url = new URL(route.request().url());
        const p = url.pathname.replace(/^\/api/, '');
        const repo = url.searchParams.get('repo') ?? REPOS.scope;
        const current =
            repo === REPOS.design
                ? 'design'
                : repo === REPOS.plan
                  ? 'intent+plan'
                  : repo === REPOS.build
                    ? 'build+ship'
                    : 'scope';
        const body = (data: unknown) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(contractFixture(data, [])),
            });
        switch (p) {
            case '/fleet':
            case '/fleet/refresh':
                return body({ stale_since: null, stale_reason: '', projects: FLEET });
            case '/studios':
                return body({ studios: STUDIOS });
            case '/maintenance/inbox':
                return body({ items: INBOX, scanned: true });
            case '/agents':
                return body({ agents: AGENTS });
            case '/runs':
                return body({ runs: RUNS });
            case '/runs/graph':
                return body(GRAPH);
            case '/deliveries/overview':
            case '/deliveries/state':
                return body(overview(repo, current));
            case '/deliveries/config':
                return body(overview(repo, current).config);
            case '/deliveries/substance': {
                const phase = url.searchParams.get('phase');
                if (phase === 'scope' && repo === REPOS.scope) return body(SCOPE_SUBSTANCE);
                if (phase === 'intent+plan') return body({ claims: CLAIMS });
                return body({});
            }
            case '/deliveries/file':
                return body({
                    path: url.searchParams.get('path'),
                    content: RECORD,
                    size: RECORD.length,
                });
            case '/deliveries/tree':
                return body({ tree: TREE });
            case '/maintenance/state':
                return body(MAINTENANCE);
            case '/promotion/state':
                return body(PROMOTION);
            case '/promotion/options':
                return body({
                    repo,
                    readable: true,
                    installs: [{ install: 'example', entry: 'prod', environments: [] }],
                });
            case '/config/session':
                return body({ oidc_enabled: true, sign_out_url: '/oauth2/sign_out' });
            case '/config/git-identities':
                return body({
                    identities: [
                        {
                            name: 'foundry-bot',
                            email: 'bot@example.test',
                            login: 'foundry-bot',
                            configured: true,
                        },
                        {
                            name: 'foundry-review',
                            email: 'review@example.test',
                            login: 'foundry-review',
                            configured: false,
                        },
                    ],
                });
            case '/config/git-roles':
                return body({
                    roles: { builder: 'foundry-bot', review: 'foundry-review' },
                    catalog: [
                        { key: 'architect', label: 'Architect', kind: 'delivery' },
                        { key: 'builder', label: 'Builder', kind: 'delivery' },
                        { key: 'resolve', label: 'Resolve', kind: 'maintenance' },
                        { key: 'review', label: 'Review', kind: 'maintenance' },
                        { key: 'console', label: 'Console', kind: 'console' },
                    ],
                });
            case '/config/pair-credentials':
                return body({
                    credentials: [
                        {
                            name: 'partner-pair',
                            host: 'github.com',
                            login: 'partner-bot',
                            configured: true,
                        },
                    ],
                });
            case '/config/mcp-doors':
                return body({ doors: [] });
            case '/config/driver':
                return body({
                    base_url: '',
                    model: 'sonnet',
                    configured: true,
                    agent: 'house-claude',
                });
            case '/config/setting/run-retention':
                return body({});
            default:
                return body({});
        }
    });
}

interface Combo {
    el: string;
    fg: string;
    bg: string;
    ratio: number;
    need: number;
    sample: string;
}

/** Every visible text node against its composited background, WCAG 2.x contrast. Runs in the
 * page. Decorative glyph-only nodes, aria-hidden subtrees, screen-reader-only text and inactive
 * controls are out of scope, as they are for WCAG. */
const scan = (): Combo[] => {
    type Rgba = { r: number; g: number; b: number; a: number };
    const parse = (s: string): Rgba | null => {
        const m = (s || '').match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const p = m[1].split(/[\s,/]+/).map(Number);
        return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    };
    const over = (top: Rgba, under: Rgba): Rgba => {
        const a = top.a + under.a * (1 - top.a);
        const mix = (t: number, u: number) => (t * top.a + u * under.a * (1 - top.a)) / a;
        return { r: mix(top.r, under.r), g: mix(top.g, under.g), b: mix(top.b, under.b), a };
    };
    const lum = (c: Rgba) => {
        const f = (v: number) => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        };
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
    };
    const ratio = (a: Rgba, b: Rgba) => {
        const la = lum(a),
            lb = lum(b);
        return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
    };
    const hex = (c: Rgba) =>
        '#' + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
    const backgroundOf = (el: Element): Rgba => {
        const chain: Element[] = [];
        for (let e: Element | null = el; e; e = e.parentElement) chain.push(e);
        let acc: Rgba = { r: 255, g: 255, b: 255, a: 1 };
        for (const e of chain.reverse()) {
            const c = parse(getComputedStyle(e).backgroundColor);
            if (c && c.a > 0) acc = over(c, acc);
        }
        return acc;
    };
    // WCAG 1.4.3 exempts inactive controls and text that is not presented visually; hidden-
    // from-assistive-tech text is still seen, so aria-hidden is not an exemption.
    const excluded = (el: Element) =>
        el.closest('.sr-only, :disabled, [aria-disabled="true"]') !== null;
    const signature = (el: Element) => {
        const cls = (typeof el.className === 'string' ? el.className : '')
            .split(/\s+/)
            .filter((c) => /^(bg-|text-|border|opacity)/.test(c))
            .join(' ');
        return `${el.tagName.toLowerCase()} ${cls}`.trim();
    };
    const seen = new Map<string, Combo>();
    for (const el of Array.from(document.querySelectorAll('body *'))) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0)
            continue;
        if (excluded(el)) continue;
        const own = Array.from(el.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? '').trim())
            .map((n) => (n.textContent ?? '').trim())
            .join(' ');
        if (!own || !/[A-Za-z0-9]/.test(own)) continue;
        const fgRaw = parse(cs.color);
        if (!fgRaw) continue;
        const bg = backgroundOf(el);
        const fg = over(fgRaw, bg);
        const size = parseFloat(cs.fontSize);
        const weight = parseInt(cs.fontWeight, 10) || 400;
        const need = size >= 24 || (size >= 18.66 && weight >= 700) ? 3 : 4.5;
        const r = ratio(fg, bg);
        // One entry per look AND threshold: a large heading must never stand in for the small
        // text beside it, whose bar is higher.
        const key = `${signature(el)}|${hex(fg)}|${hex(bg)}|${need}`;
        const prior = seen.get(key);
        if (prior) {
            if (r < prior.ratio) prior.ratio = r;
            continue;
        }
        seen.set(key, {
            el: signature(el),
            fg: hex(fg),
            bg: hex(bg),
            ratio: r,
            need,
            sample: own.slice(0, 40),
        });
    }
    return Array.from(seen.values())
        .filter((c) => c.ratio < c.need)
        .map((c) => ({ ...c, ratio: Math.round(c.ratio * 100) / 100 }));
};

const failures = async (page: Page, view: string) => {
    const fails = await page.evaluate(scan);
    return fails.map(
        (f) => `${view}: ${f.ratio}:1 (needs ${f.need}) ${f.el} "${f.sample}" ${f.fg} on ${f.bg}`,
    );
};

const q = (repo: string) => encodeURIComponent(repo);
/** A cockpit loads a phase's content on demand. */
const loadPhase = (page: Page) =>
    page.getByRole('button', { name: 'Load phase content', exact: true }).click();

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

/** Each view: where to go, what proves it rendered with its data, and the tabs to walk. */
const VIEWS: {
    name: string;
    url: string;
    ready: (page: Page) => Promise<void>;
    tabs?: string[];
    viewport?: { width: number; height: number };
}[] = [
    {
        name: 'fleet',
        url: '/',
        ready: async (page) => expect(page.getByRole('table')).toBeVisible(),
    },
    {
        name: 'delivery scope',
        url: `/d?repo=${q(REPOS.scope)}`,
        ready: async (page) => {
            await loadPhase(page);
            await expect(page.getByRole('tab', { name: /^Overview/ })).toBeVisible();
        },
        tabs: [
            'Overview',
            'Estimate',
            'Requirements',
            'Phases',
            'Assumptions',
            'Architecture',
            'Record',
        ],
    },
    {
        name: 'delivery scope (phone)',
        url: `/d?repo=${q(REPOS.scope)}`,
        ready: async (page) => {
            await loadPhase(page);
            await expect(page.getByRole('tab', { name: /^Overview/ })).toBeVisible();
        },
        viewport: PHONE,
    },
    {
        name: 'delivery design (record only)',
        url: `/d?repo=${q(REPOS.design)}`,
        ready: async (page) => {
            await loadPhase(page);
            await expect(
                page.getByText(/the substance is the estimation project itself/),
            ).toBeVisible();
        },
    },
    {
        name: 'delivery intent+plan',
        url: `/d?repo=${q(REPOS.plan)}`,
        ready: async (page) => {
            await loadPhase(page);
            await expect(page.getByText('INT-ACME-001')).toBeVisible();
        },
    },
    {
        name: 'delivery build+ship',
        url: `/d?repo=${q(REPOS.build)}`,
        ready: async (page) => {
            await loadPhase(page);
            await page.getByRole('button', { name: 'Load file tree', exact: true }).click();
            await expect(page.getByText('README.md')).toBeVisible();
        },
    },
    {
        name: 'maintenance',
        url: `/d?repo=${q(REPOS.build)}&mode=maintenance`,
        ready: async (page) =>
            expect(page.getByText('The phone layout stops at 384 px')).toBeVisible(),
    },
    {
        name: 'promotion',
        url: `/d?repo=${q(REPOS.build)}&mode=promotion`,
        ready: async (page) =>
            expect(page.getByText('example-prod', { exact: true })).toBeVisible(),
    },
    {
        name: 'settings',
        url: '/settings',
        ready: async (page) => {
            await expect(page.getByText(/foundry-review/).first()).toBeVisible();
            await expect(page.getByText('Resolve', { exact: true }).first()).toBeVisible();
        },
    },
    {
        name: 'studios',
        url: '/studios',
        ready: async (page) => expect(page.getByText('unreachable').first()).toBeVisible(),
    },
];

test.describe('light mode reads: every visible text node clears WCAG contrast', () => {
    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            localStorage.setItem('rb.appearance', 'light');
            localStorage.setItem('rb.motion', 'off');
        });
        await stubApi(page);
    });

    for (const view of VIEWS) {
        test(view.name, async ({ page }) => {
            await page.setViewportSize(view.viewport ?? DESKTOP);
            await page.goto(view.url);
            await view.ready(page);
            expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('light');
            const fails: string[] = [];
            if (view.tabs) {
                for (const tab of view.tabs) {
                    await page.getByRole('tab', { name: new RegExp('^' + tab) }).click();
                    fails.push(...(await failures(page, `${view.name} / ${tab}`)));
                }
            } else {
                fails.push(...(await failures(page, view.name)));
            }
            expect(fails, fails.join('\n')).toEqual([]);
        });
    }
});
