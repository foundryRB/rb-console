import { useCopilot } from '@/viewmodels/copilot';
import { useStudios } from '@/viewmodels/studios';
import { useFleet } from '@/viewmodels/fleet';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import type { FleetItem } from '@/models';
import { cn } from '@/utils';
import { useDeliveries } from '@/viewmodels/deliveries';
import { useMaintenance } from '@/viewmodels/maintenance';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Cockpit } from '@/views/templates/Cockpit';
import { StartDeliveryForm } from '@/views/organisms/StartDeliveryForm';
import { StudiosStrip } from '@/views/molecules/StudiosStrip';
import { CoPilotPanel } from '@/views/organisms/CoPilotPanel';
import { ProjectTile } from '@/views/molecules/ProjectTile';
import { SortHeading } from '@/views/atoms/SortHeading';

import { ProjectSignals } from '@/views/molecules/ProjectSignals';

import { InboxStrip } from '@/views/organisms/InboxStrip';
import { ProjectLive } from '@/views/molecules/ProjectLive';

import { ProjectLinks } from '@/views/molecules/ProjectLinks';
import { ProjectName } from '@/views/molecules/ProjectName';
import { ProjectDelivery } from '@/views/molecules/ProjectDelivery';
import {
    type Filter,
    FILTER_LABEL,
    matchesQuery,
    matches,
    sentence,
    cockpitHref,
    type SortKey,
    deliveryRank,
    liveRank,
    isDesktop,
} from '@/viewmodels/fleet/fleet.model';

export const DeliveriesPage: React.FC = () => {
    const {
            fleet,
            fleetLoading,
            fleetError,
            freshness,
            loadFleet,
            refreshFleetNow,
            fleetRefreshedAt,
            fleetRefreshError,
            fleetRefreshPending,
            fleetStaleSince,
            fleetStaleReason,
            pauseApp,
            resumeApp,
        } = useFleet(),
        { studios, loadStudios } = useStudios(),
        { actionLoading } = useDeliveries(),
        {
            fleetChat,
            fleetChatBusy,
            fleetChatConfigured,
            fleetChatModel,
            sendFleetChat,
            clearFleetChat,
        } = useCopilot();
    const { inbox, loadInbox } = useMaintenance();
    const navigate = useNavigate();
    // Every project opens its cockpit: a delivery lands on its line, a live or bare repo
    // lands on the project view (worktree + live app + co-pilot, and a way to open a line).
    const openDelivery = (p: FleetItem) => navigate(cockpitHref(p.repo));
    // Middle-click (the "open in a new tab" gesture) on the row's own space opens the cockpit
    // in a new tab, the way a real link would - but NOT when the click lands on an inner <a>
    // (docs, GitHub, the delivery link), which owns its own target. onMouseDown swallows the
    // middle button so the browser's autoscroll puck never appears.
    const openAux = (p: FleetItem) => (e: React.MouseEvent) => {
        if (e.button === 1 && !(e.target as HTMLElement).closest('a')) {
            e.preventDefault();
            window.open(cockpitHref(p.repo), '_blank', 'noopener,noreferrer');
        }
    };
    const suppressMiddle = (e: React.MouseEvent) => {
        if (e.button === 1 && !(e.target as HTMLElement).closest('a')) e.preventDefault();
    };
    const [showStart, setShowStart] = useState(false);
    const [showPilot, setShowPilot] = useState(isDesktop);
    const [view, setView] = useState<'table' | 'tiles'>(() => (isDesktop() ? 'table' : 'tiles'));
    const [filter, setFilter] = useState<Filter>('all');
    // The project search lives in the URL (?q=), so a filtered view is a shareable link - the
    // ticket's nice-to-have - and a reload keeps the term. `replace` so typing does not stack a
    // history entry per keystroke; the param is dropped, not left blank, when the box is cleared.
    const [searchParams, setSearchParams] = useSearchParams();
    const q = searchParams.get('q') ?? '';
    const setSearch = (next: string) =>
        setSearchParams(
            (prev) => {
                const p = new URLSearchParams(prev);
                if (next.trim()) p.set('q', next);
                else p.delete('q');
                return p;
            },
            { replace: true },
        );
    const [sortKey, setSortKey] = useState<SortKey | null>(null);
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
    const onSort = (k: SortKey) => {
        if (sortKey === k) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        else {
            setSortKey(k);
            setSortDir('asc');
        }
    };

    useEffect(() => {
        void loadFleet();
        void loadStudios();
        void loadInbox();
    }, [loadFleet, loadStudios, loadInbox]);

    // Force a refresh now: the board is served from the server's warm cache that only turns
    // over every configured interval (issue #27), so the control asks the server for a rescan
    // NOW (POST /fleet/refresh, INT-FC-R107) and then re-pulls the inbox and the studios,
    // which that rescan just recomputed. Awaited end to end, so the glyph spins for the whole
    // act, and the ✓ flash fires only for a rescan that actually landed.
    const [refreshFlash, setRefreshFlash] = useState(false);
    const refreshFleet = async () => {
        const ok = await refreshFleetNow();
        await Promise.all([loadStudios(), loadInbox()]);
        if (ok) {
            setRefreshFlash(true);
            window.setTimeout(() => setRefreshFlash(false), 2500);
        }
    };

    // The per-repo attention counts, for the fourth signal chip.
    const attention = useMemo(() => {
        const counts: Record<string, number> = {};
        for (const it of inbox) counts[it.repo] = (counts[it.repo] ?? 0) + 1;
        return counts;
    }, [inbox]);

    const stats = useMemo(() => {
        // In delivery = has a live scratch ref (see matches('delivery')); a delivered line
        // stays counted until Close-line removes it, so the tile and the row never disagree.
        const inDelivery = fleet.filter((p) => p.is_delivery).length;
        const awaiting = fleet.filter((p) => p.delivery_status === 'awaiting-gate').length;
        const live = fleet.filter((p) => p.live === 'running').length;
        const onboarded = fleet.filter((p) => p.onboarded).length;
        return { inDelivery, awaiting, live, onboarded };
    }, [fleet]);

    const hasDeliveries = fleet.some((p) => p.is_delivery);
    const query = q.trim().toLowerCase();
    const searching = query !== '';
    const shown = useMemo(
        () => fleet.filter((p) => matches(p, filter) && matchesQuery(p, query)),
        [fleet, filter, query],
    );
    // Apply the column sort on top of the filter. No key = the backend's discovery order.
    const sortedShown = useMemo(() => {
        if (!sortKey) return shown;
        const dir = sortDir === 'asc' ? 1 : -1;
        const byName = (a: FleetItem, b: FleetItem) => a.name.localeCompare(b.name);
        return [...shown].sort((a, b) => {
            if (sortKey === 'project') return byName(a, b) * dir;
            if (sortKey === 'live') return (liveRank(a) - liveRank(b)) * dir || byName(a, b);
            return (deliveryRank(a) - deliveryRank(b)) * dir || byName(a, b);
        });
    }, [shown, sortKey, sortDir]);
    // Split the floor by manifest role (ADR-032): the apps the Foundry BUILDS AND RUNS (output,
    // and everything that joins no manifest app - bare repos, in-flight deliveries) are the main
    // fleet; the apps that MAKE UP the Foundry itself (parts) gather in one labelled group. The
    // grouping is the whole distinction - no second status colour competing with paused. Collapsed
    // by default: the platform set is small, fixed, and soon the minority, so it reads as the
    // substrate tucked under the tenant fleet, one click from view. Sort/filter apply within each.
    // 'core' joins 'parts' in this group rather than earning a fourth band: the group's whole
    // meaning is "what the Foundry is, not what it delivers", and the platform repo and the
    // playbook are that more completely than any app in it. They sort to the TOP of the group,
    // ahead of the column sort, because they are what the rest of it is built out of - and
    // because a row that can never be onboarded reads as broken sitting among ones that are.
    // repo -> the app's fleet name, for the rows that carry one. The inbox knows only a
    // repository, and the ArgoCD Application it deep-links to is named for the app, so the
    // strip resolves the one from the other through the board it sits above.
    const appNamesByRepo = useMemo(
        () =>
            Object.fromEntries(
                fleet.filter((p) => p.app_name).map((p) => [p.repo, p.app_name]),
            ) as Record<string, string>,
        [fleet],
    );
    const isCore = (p: FleetItem) => p.role === 'parts' || p.role === 'core';
    const coreShown = useMemo(
        () =>
            sortedShown
                .filter(isCore)
                .slice()
                .sort((a, b) => Number(b.role === 'core') - Number(a.role === 'core')),
        [sortedShown],
    );
    const restShown = useMemo(() => sortedShown.filter((p) => !isCore(p)), [sortedShown]);
    const [coreOpen, setCoreOpen] = useState(false);
    // A running search reveals the Foundry-core group unconditionally: a match that lives only
    // among the parts apps must not stay hidden behind the collapse, or the search would read as
    // "no matches" while the app it found sat one click away.
    const coreExpanded = coreOpen || searching;
    const toggle = (f: Filter) => setFilter((cur) => (cur === f ? 'all' : f));

    // The refresh outcome and its tone, chosen together so a neutral note never reads as red.
    const refreshOutcome = fleetRefreshError
        ? { text: `Refresh failed: ${fleetRefreshError}`, tone: 'text-destructive' }
        : fleetRefreshPending
          ? { text: 'Still refreshing - the board will catch up', tone: 'text-muted-foreground' }
          : fleetStaleSince
            ? { text: 'Held - the org could not be read', tone: 'text-muted-foreground' }
            : fleetError && fleet.length > 0
              ? { text: `Showing the last board - ${fleetError}`, tone: 'text-destructive' }
              : refreshFlash
                ? { text: 'Refreshed', tone: 'text-[hsl(var(--success))]' }
                : {
                      text: fleetRefreshedAt ? `Updated ${fleetRefreshedAt}` : '',
                      tone: 'text-muted-foreground',
                  };

    // The fleet's controls ride the masthead; a second header row below it wastes a line.
    const bar = (
        <>
            <StudiosStrip studios={studios} />
            <span className="flex-1" />
            {/* The refresh outcome, shown and spoken: a persistent polite live region, so the
                result is announced rather than only drawn. The error names a failed forced
                rescan, or a failed board read while the last rows stay on screen; otherwise the
                last landed rescan's time keeps the control honest about the board's age.

                A rescan the SPA stopped waiting on is a third outcome, neither of those: it
                is still running server-side and the board will carry it once it lands, so it
                reads as a neutral note rather than a red failure (issue #39). */}
            <span role="status" className={cn('text-xs', refreshOutcome.tone)}>
                {refreshOutcome.text}
            </span>
            {/* A quiet manual refresh (issue #27), sitting with the view controls so it reads as
                a utility, not a call to action. It is an explicit rescan-now, not a cache
                re-read; the glyph spins while the rescan runs (doubling as the ambient refresh
                indicator for the mount's loads) and flashes ✓ when a forced rescan lands. */}
            <button
                type="button"
                onClick={() => void refreshFleet()}
                disabled={fleetLoading}
                aria-busy={fleetLoading}
                aria-label="Refresh the fleet now"
                title="Rescan the fleet, inbox, and studios now"
                className={cn(
                    'inline-flex h-7 w-7 flex-none items-center justify-center rounded-md border border-border text-muted-foreground hover:text-foreground disabled:cursor-default disabled:opacity-70',
                    refreshFlash && 'border-[hsl(var(--success))] text-[hsl(var(--success))]',
                )}
            >
                <span
                    aria-hidden="true"
                    className={cn('text-sm leading-none', fleetLoading && 'animate-spin')}
                >
                    {refreshFlash ? '✓' : '↻'}
                </span>
            </button>
            <div className="flex overflow-hidden rounded-md border border-border text-xs">
                {(['table', 'tiles'] as const).map((v) => (
                    <button
                        key={v}
                        type="button"
                        onClick={() => setView(v)}
                        className={cn(
                            'px-2.5 py-1 capitalize',
                            view === v
                                ? 'bg-primary/15 text-link'
                                : 'text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {v}
                    </button>
                ))}
            </div>
            <Button
                type="button"
                variant={showPilot ? 'default' : 'outline'}
                onClick={() => setShowPilot((s) => !s)}
                title="The home co-pilot: your saved home provider, advising over the whole floor"
            >
                Co-pilot
            </Button>
            <Button type="button" onClick={() => setShowStart((s) => !s)}>
                {showStart ? 'Close' : 'New delivery'}
            </Button>
        </>
    );

    // One table row / one tile for a project, so the main fleet and the Foundry-core group render
    // the exact same cell without duplicating the markup.
    const renderRow = (p: FleetItem) => (
        <tr
            key={p.repo}
            onClick={() => openDelivery(p)}
            onAuxClick={openAux(p)}
            onMouseDown={suppressMiddle}
            title="Open the project cockpit (middle-click for a new tab)"
            className={cn(
                'cursor-pointer border-b border-border last:border-0 hover:bg-primary/5',
                p.live === 'paused' && 'bg-amber-500/15',
                p.hidden && 'opacity-55',
            )}
        >
            <td className="px-4 py-3">
                <ProjectName p={p} />
            </td>
            <td className="px-4 py-3">
                <ProjectDelivery p={p} />
            </td>
            <td className="px-4 py-3">
                <ProjectSignals p={p} attention={attention[p.repo]} />
            </td>
            <td className="px-4 py-3">
                <ProjectLive
                    p={p}
                    busy={actionLoading}
                    onPause={() => void pauseApp(p.app_name || p.name)}
                    onResume={() => void resumeApp(p.app_name || p.name)}
                />
            </td>
            <td className="px-4 py-3">
                <span className="vf-project-actions inline-flex flex-wrap items-center gap-2">
                    <Link
                        to={cockpitHref(p.repo)}
                        onClick={(e) => e.stopPropagation()}
                        className="text-[11px] text-link hover:underline"
                        title="Open the project cockpit (middle-click for a new tab)"
                    >
                        open ↗
                    </Link>
                    <ProjectLinks p={p} />
                </span>
            </td>
        </tr>
    );

    const renderTile = (p: FleetItem) => (
        <div
            key={p.repo}
            onClick={() => openDelivery(p)}
            onAuxClick={openAux(p)}
            onMouseDown={suppressMiddle}
            title="Open the project cockpit (middle-click for a new tab)"
            className={cn(
                'flex cursor-pointer flex-col gap-2 rounded-lg border bg-card p-4 hover:border-link/50',
                p.hidden
                    ? 'border-dashed border-muted-foreground/40 opacity-70'
                    : p.live === 'paused'
                      ? 'border-amber-500/40 bg-amber-500/15'
                      : 'border-border',
            )}
        >
            <div className="flex items-start justify-between gap-2">
                <ProjectName p={p} />
                <ProjectLive
                    p={p}
                    busy={actionLoading}
                    onPause={() => void pauseApp(p.app_name || p.name)}
                    onResume={() => void resumeApp(p.app_name || p.name)}
                />
            </div>
            <div className="text-xs">
                <ProjectDelivery p={p} />
            </div>
            <ProjectSignals p={p} attention={attention[p.repo]} />
            <ProjectLinks p={p} />
        </div>
    );

    // The one control that sets the Foundry-core group apart: a neutral, colourless disclosure -
    // no fill, no hue - so it groups the platform apps without adding a colour that would compete
    // with the paused-app amber. Same button in the table (a spanning row) and the tiles (a band).
    const coreToggleButton = (
        <button
            type="button"
            onClick={() => setCoreOpen((v) => !v)}
            aria-expanded={coreExpanded}
            title="What the Foundry IS - the platform repo and the playbook it runs on, plus the apps it is made of - rather than the apps it delivers"
            className="inline-flex w-full items-baseline gap-2 text-left text-muted-foreground hover:text-foreground"
        >
            <span aria-hidden="true" className="font-mono text-[10px]">
                {coreExpanded ? '▾' : '▸'}
            </span>
            <span className="text-[11px] font-medium uppercase tracking-wide">Foundry core</span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] tabular-nums">
                {coreShown.length}
            </span>
        </button>
    );

    return (
        <Cockpit bar={bar} aside={fleet.length > 0 ? `${fleet.length} projects` : undefined}>
            {showStart && (
                <div className="mb-6">
                    <StartDeliveryForm
                        onStarted={(established) => {
                            // Confirm the act by landing on the new delivery's cockpit: the repo,
                            // the derived phase (pre-scope), and the Drive control that is the
                            // actual next step. Establish and run are two steps by design, so this
                            // closes the loop instead of vanishing onto a not-yet-refreshed fleet
                            // (issue #53). Navigating unmounts this page, so the fleet re-derives on
                            // return - no un-awaited loadFleet racing the panel close.
                            setShowStart(false);
                            navigate(cockpitHref(established.repo));
                        }}
                    />
                </div>
            )}

            <div
                className={cn(
                    showPilot &&
                        'grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(300px,min(22vw,360px))]',
                )}
            >
                <div className="vf-fleet-board min-w-0">
                    <InboxStrip items={inbox} appNames={appNamesByRepo} />
                    {/* Search the board by name as you type (issue #55). Matches the app name or its
                owner/name slug - the two identifiers a row shows - and rides the URL (?q=) so a
                filtered view is a shareable link. Sits above the list so it reads as the board's
                own filter, beside the stat tiles it composes with. */}
                    <div className="relative mb-3 max-w-xs">
                        <span
                            aria-hidden="true"
                            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground"
                        >
                            ⌕
                        </span>
                        <Input
                            type="text"
                            value={q}
                            onChange={(e) => setSearch(e.target.value)}
                            aria-label="Search projects by name"
                            placeholder="Search projects..."
                            className="pl-8 pr-8"
                        />
                        {searching && (
                            <button
                                type="button"
                                onClick={() => setSearch('')}
                                aria-label="Clear search"
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                            >
                                ×
                            </button>
                        )}
                    </div>
                    <div
                        className={cn(
                            'grid grid-cols-2 gap-3 sm:grid-cols-4',
                            filter === 'all' ? 'mb-5' : 'mb-2',
                        )}
                    >
                        <ProjectTile
                            n={stats.inDelivery}
                            label="In delivery"
                            accent="text-link"
                            active={filter === 'delivery'}
                            onClick={() => toggle('delivery')}
                        />
                        <ProjectTile
                            n={stats.awaiting}
                            label="Awaiting a gate"
                            active={filter === 'awaiting'}
                            onClick={() => toggle('awaiting')}
                        />
                        <ProjectTile
                            n={stats.live}
                            label="Live"
                            accent="text-[hsl(var(--success))]"
                            active={filter === 'live'}
                            onClick={() => toggle('live')}
                        />
                        <ProjectTile
                            n={stats.onboarded}
                            label="Onboarded"
                            active={filter === 'onboarded'}
                            onClick={() => toggle('onboarded')}
                        />
                    </div>

                    {filter !== 'all' && (
                        <div className="mb-5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                            <span className="font-semibold uppercase tracking-wider">Filter</span>
                            <span>
                                showing{' '}
                                <span className="font-medium text-link">
                                    {FILTER_LABEL[filter]}
                                </span>{' '}
                                ({shown.length}){' · '}
                                <button
                                    type="button"
                                    onClick={() => setFilter('all')}
                                    className="text-link hover:underline"
                                >
                                    clear
                                </button>
                            </span>
                        </div>
                    )}

                    {/* The board is HELD, not current (INT-FC-R144): the server's org read is failing
                and it is still answering the last good scan. The rows look exactly as they
                would if they were current, so this banner is the only thing standing between
                the operator and acting on a floor that has moved on. Only when there IS a held
                board - with no rows there is no last good scan to have been held, and the
                empty state below tells that story properly instead. */}
                    {fleetStaleSince && fleet.length > 0 && (
                        <div className="mb-4 rounded-lg border border-dashed border-destructive/50 bg-destructive/5 px-4 py-3 text-xs">
                            <span className="font-medium text-destructive">
                                Board held since {fleetStaleSince}
                            </span>
                            <span className="text-muted-foreground">
                                {' '}
                                - showing the last good scan rather than the current floor.
                                {fleetStaleReason ? ` ${sentence(fleetStaleReason)}` : ''}
                            </span>
                        </div>
                    )}

                    {fleet.length === 0 && !fleetLoading && (
                        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16 text-center">
                            {/* Only blame the token when the scan actually RAN and found nothing. A
                        failed scan that blamed it sent operators to Settings to re-enter a
                        token that was never the problem. */}
                            <p className="text-sm font-medium">
                                {fleetStaleSince || fleetError || freshness?.state === 'unavailable'
                                    ? 'The floor could not be read'
                                    : freshness?.state === 'loading' ||
                                        (freshness && !freshness.coverage.complete)
                                      ? 'Observation pending'
                                      : 'No projects yet'}
                            </p>
                            <p className="mt-1 text-xs text-muted-foreground">
                                {fleetStaleSince ||
                                fleetError ||
                                freshness?.state === 'unavailable' ? (
                                    <>
                                        The last scan could not be made, and there is no earlier one
                                        to fall back to.{' '}
                                        {sentence(
                                            fleetStaleReason ||
                                                fleetError ||
                                                freshness?.reason_code ||
                                                '',
                                        )}
                                    </>
                                ) : freshness?.state === 'loading' ||
                                  (freshness && !freshness.coverage.complete) ? (
                                    <>The scheduled observation is still incomplete.</>
                                ) : (
                                    <>
                                        Set the git token in{' '}
                                        <span className="text-foreground">Settings</span> to
                                        discover the org.
                                    </>
                                )}
                            </p>
                        </div>
                    )}

                    {fleet.length > 0 && !hasDeliveries && (
                        <div className="mb-4 rounded-lg border border-dashed border-link/40 bg-primary/5 px-4 py-3 text-xs text-muted-foreground">
                            No deliveries in flight - these are onboarded apps and plain repos. Any
                            row opens its project cockpit;{' '}
                            <span className="text-link">New delivery</span> opens a line.
                        </div>
                    )}

                    {fleet.length > 0 && shown.length === 0 && (
                        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
                            {searching ? (
                                <>No projects match &ldquo;{q}&rdquo;. </>
                            ) : (
                                <>No projects match this filter. </>
                            )}
                            <button
                                type="button"
                                onClick={() => {
                                    setFilter('all');
                                    setSearch('');
                                }}
                                className="text-link hover:underline"
                            >
                                Clear
                            </button>
                        </div>
                    )}

                    {shown.length > 0 && view === 'table' && (
                        <div className="app-glass overflow-hidden rounded-lg border border-border">
                            <div className="overflow-x-auto">
                                <table className="vf-fleet-table w-full min-w-[820px] text-sm">
                                    <thead>
                                        <tr className="border-b border-border bg-secondary/40 text-[11px] uppercase tracking-wide text-muted-foreground">
                                            <SortHeading
                                                label="Project"
                                                sortKey="project"
                                                active={sortKey}
                                                dir={sortDir}
                                                onSort={onSort}
                                            />
                                            <SortHeading
                                                label="Delivery"
                                                sortKey="delivery"
                                                active={sortKey}
                                                dir={sortDir}
                                                onSort={onSort}
                                            />
                                            <th className="px-4 py-2.5 text-left font-medium">
                                                Signals
                                            </th>
                                            <SortHeading
                                                label="Live"
                                                sortKey="live"
                                                active={sortKey}
                                                dir={sortDir}
                                                onSort={onSort}
                                            />
                                            <th className="px-4 py-2.5 text-left font-medium">
                                                Open
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {restShown.map(renderRow)}
                                        {coreShown.length > 0 && (
                                            <tr className="border-t-2 border-border/80 bg-secondary/30">
                                                <td colSpan={5} className="px-4 py-2">
                                                    {coreToggleButton}
                                                </td>
                                            </tr>
                                        )}
                                        {coreExpanded && coreShown.map(renderRow)}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {shown.length > 0 && view === 'tiles' && (
                        <>
                            {restShown.length > 0 && (
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                    {restShown.map(renderTile)}
                                </div>
                            )}
                            {coreShown.length > 0 && (
                                <div className={cn(restShown.length > 0 && 'mt-4')}>
                                    <div className="mb-3 rounded-md border border-border bg-secondary/30 px-3 py-2">
                                        {coreToggleButton}
                                    </div>
                                    {coreExpanded && (
                                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                            {coreShown.map(renderTile)}
                                        </div>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>
                {showPilot && (
                    <Card className="flex h-[70vh] flex-col p-4 lg:sticky lg:top-4 lg:h-[calc(100dvh-6.5rem)]">
                        <CoPilotPanel
                            messages={fleetChat}
                            busy={fleetChatBusy}
                            configured={fleetChatConfigured}
                            model={fleetChatModel}
                            references={[]}
                            onSend={(m) => void sendFleetChat(m)}
                            onClear={clearFleetChat}
                            onToggleReference={() => undefined}
                            notConfiguredHint={<>Choose a provider in Settings · Home co-pilot.</>}
                            emptyHint="Ask about a delivery or next action."
                        />
                    </Card>
                )}
            </div>
        </Cockpit>
    );
};
export default DeliveriesPage;
