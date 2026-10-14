import type { FleetItem, MaintInboxItem } from '@/models';
import { githubUrl, projectLinks } from '@/utils';

export type Filter = 'all' | 'delivery' | 'awaiting' | 'live' | 'onboarded';

export const FILTER_LABEL: Record<Filter, string> = {
    all: 'all projects',
    delivery: 'in delivery',
    awaiting: 'awaiting a gate',
    live: 'live',
    onboarded: 'onboarded',
};

export const matchesQuery = (p: FleetItem, q: string): boolean =>
    q === '' || p.name.toLowerCase().includes(q) || p.repo.toLowerCase().includes(q);

export const matches = (p: FleetItem, f: Filter): boolean => {
    switch (f) {
        case 'delivery':
            // "In delivery" = has a live scratch ref, delivered-but-not-closed
            // included: a delivery counts until Close-line removes the ref (then
            // is_delivery flips false and it leaves on its own). Excluding 'delivered'
            // made a finished line vanish from the tile while it still had a delivery.
            return p.is_delivery;
        case 'awaiting':
            return p.delivery_status === 'awaiting-gate';
        case 'live':
            return p.live === 'running';
        case 'onboarded':
            return p.onboarded;
        default:
            return true;
    }
};

export const sentence = (why: string): string =>
    why ? `${why[0].toUpperCase()}${why.slice(1)}${/[.!?]$/.test(why) ? '' : '.'}` : '';

export const cockpitHref = (repo: string): string => `/d?repo=${encodeURIComponent(repo)}`;

export type SortKey = 'project' | 'delivery' | 'live';

export const DELIVERY_RANK: Record<string, number> = {
    degraded: 0,
    'awaiting-gate': 1,
    'run-phase': 2,
    delivered: 4,
    learned: 5,
};

export const deliveryRank = (p: FleetItem): number =>
    !p.is_delivery
        ? p.onboarded
            ? 7
            : 8
        : p.activity === 'running'
          ? -1
          : (DELIVERY_RANK[p.delivery_status ?? ''] ?? 3);

export const LIVE_RANK: Record<string, number> = { running: 0, paused: 1 };

export const liveRank = (p: FleetItem): number =>
    p.onboarded ? (LIVE_RANK[p.live ?? ''] ?? 2) : 5;

export type DeliveryView = { text: string; cls: string; live: boolean };

export const withPhase = (phase: string, verb: string): string =>
    phase ? `${phase} · ${verb}` : verb;

export const deliveryView = (p: FleetItem): DeliveryView => {
    const phase = p.delivery_phase ?? '';
    if (p.activity === 'running')
        return { text: withPhase(phase, 'building'), cls: 'text-link', live: true };
    if (p.activity === 'suspended' || p.delivery_status === 'awaiting-gate')
        return {
            text: withPhase(phase, 'needs your sign-off'),
            cls: 'text-amber-400',
            live: false,
        };
    if (p.delivery_status === 'run-phase')
        return { text: withPhase(phase, 'ready to drive'), cls: 'text-amber-400', live: false };
    if (p.delivery_status === 'degraded')
        return { text: withPhase(phase, 'degraded'), cls: 'text-destructive', live: false };
    if (p.delivery_status === 'delivered')
        return { text: 'delivered', cls: 'text-[hsl(var(--success))]', live: false };
    // Learn ran (the journal carries its stamp); the one act left is the operator's close.
    if (p.delivery_status === 'learned')
        return { text: 'learned · ready to close', cls: 'text-[hsl(var(--success))]', live: false };
    return { text: p.delivery_status ?? 'in delivery', cls: 'text-foreground', live: false };
};

export const INBOX_COLLAPSED = 8;

export const slugOf = (repo: string): string => (repo.split('/').pop() ?? repo).toLowerCase();

export function inboxTarget(
    it: MaintInboxItem,
    appName: string = '',
): { to: string } | { href: string } {
    const gh = githubUrl(it.repo);
    const maint = `/d?repo=${encodeURIComponent(it.repo)}&mode=maintenance`;
    switch (it.signal) {
        case 'running':
            // A maintenance run in flight: open its Maintenance line to watch it - the run is
            // live there, nothing to re-drive. `number` is the CONCERN the run works, always a
            // ticket (a review's PR is mapped back to it server-side, INT-FC-R98), so the
            // deep-link lands on the ticket; absent for a review of a PR that resolves none.
            return { to: it.number ? `${maint}&ticket=${it.number}` : maint };
        case 'issue':
            return { to: it.number ? `${maint}&ticket=${it.number}` : maint };
        case 'pr-review':
            return { href: it.number ? `${gh}/pull/${it.number}` : `${gh}/pulls` };
        case 'red-ci':
            // A PR's red opens that PR's checks; the default branch's red carries no number
            // and belongs in the workflow runs, where the failing release run is the top row.
            return { href: it.number ? `${gh}/pull/${it.number}/checks` : `${gh}/actions` };
        case 'unreleased':
            return { href: `${gh}/commits` };
        case 'drift':
            return { href: projectLinks(slugOf(it.repo), appName).argocd };
        default:
            return { href: gh };
    }
}

export const STAGE_LABEL: Record<string, string> = {
    'in-progress': 'in progress',
    open: 'open',
    'awaiting-review': 'at a gate',
    'awaiting-merge': 'awaiting merge',
    'changes-requested': 'changes requested',
    'checks-red': 'checks red',
};

export const STAGE_CLS: Record<string, string> = {
    'in-progress': 'animate-pulse bg-primary/20 text-link',
    open: 'bg-muted text-muted-foreground',
    'awaiting-review': 'bg-primary/15 text-link',
    'awaiting-merge': 'bg-amber-400/15 text-amber-400',
    'changes-requested': 'bg-destructive/15 text-destructive',
    'checks-red': 'bg-destructive/15 text-destructive',
};

export const SIGNAL_RANK: Record<string, number> = {
    running: -1,
    'red-ci': 0,
    drift: 1,
    'pr-review': 2,
    unreleased: 3,
    issue: 4,
};

export const rankOf = (it: MaintInboxItem): number => SIGNAL_RANK[it.signal] ?? 9;

export const ageKeyOf = (it: MaintInboxItem): number => {
    const t = it.ts ? Date.parse(it.ts) : NaN;
    return Number.isNaN(t) ? Number.POSITIVE_INFINITY : t;
};

export type InboxSort = 'criticality' | 'project' | 'age';

export const SORT_NAME: Record<InboxSort, string> = {
    criticality: 'attention',
    project: 'project',
    age: 'age',
};

export const SORT_OPTIONS: InboxSort[] = ['criticality', 'project', 'age'];

export const triggerCls =
    'inline-flex max-w-[9rem] items-center gap-1 rounded border border-border bg-transparent px-1.5 py-0.5 font-mono text-[10px] leading-4 text-muted-foreground hover:text-foreground focus:outline-none';

export const panelCls =
    'absolute right-0 top-full z-20 mt-1 max-h-56 w-44 overflow-auto rounded border border-border bg-card p-1 shadow-lg';

export const optionCls =
    'flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-1 text-[11px] text-foreground hover:bg-secondary/60';

export const isDesktop = (): boolean =>
    typeof window === 'undefined' || window.matchMedia('(min-width: 1024px)').matches;
