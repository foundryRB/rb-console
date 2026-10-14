import { ObservationNotice } from '@/views/atoms/ObservationNotice';
import { useFleet } from '@/viewmodels/fleet';
import { lastRefusal, useRuns } from '@/viewmodels/runs';
import { useCopilot } from '@/viewmodels/copilot';
import { useAgents } from '@/viewmodels/agents';
import { callerOf } from '@/viewmodels/agents/agentChoices.model';
import { useSettings } from '@/viewmodels/settings';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import { cn, projectLinks } from '@/utils';
import { EMPTY_CHAT, chatKey } from '@/viewmodels/copilot';
import { repoName, selectPendingGate, useDeliveries } from '@/viewmodels/deliveries';
import { Cockpit } from '@/views/templates/Cockpit';
import { PaneToggle } from '@/views/atoms/PaneToggle';
import { SeedBadge } from '@/views/atoms/SeedBadge';
import { StatusBadge } from '@/views/atoms/StatusBadge';
import { RecordDocument } from '@/views/organisms/RecordDocument';
import { ActionPanel } from '@/views/molecules/ActionPanel';
import { CoPilotPanel } from '@/views/organisms/CoPilotPanel';
import { DeliveryConfigStrip } from '@/views/molecules/DeliveryConfigStrip';
import { DeliveryLine } from '@/views/molecules/DeliveryLine';
import { DeliveryModelForm } from '@/views/organisms/DeliveryModelForm';
import { DesignPane } from '@/views/organisms/DesignPane';
import { DriveResultPanel } from '@/views/molecules/DriveResultPanel';
import { RunBand } from '@/views/organisms/RunBand';
import { ScopePane } from '@/views/organisms/ScopePane';
import { WorktreePanel } from '@/views/organisms/WorktreePanel';
import { MaintenancePane } from '@/views/organisms/MaintenancePane';
import { PromotionPane } from '@/views/organisms/PromotionPane';
import { StartDeliveryForm } from '@/views/organisms/StartDeliveryForm';
import { RunButton } from '@/views/atoms/RunButton';
import { EmptyPane } from '@/views/atoms/EmptyPane';
import {
    runEnded,
    type BuildTab,
    EMPTY_TREE,
    EMPTY_REFS,
} from '@/viewmodels/deliveries/deliveryPresentation.model';

export const DeliveryDetailPage: React.FC = () => {
    const [params] = useSearchParams();
    const repo = params.get('repo') ?? '';
    // A ?ticket=N deep-links the Maintenance pane straight to that ticket's cockpit (the Inbox's
    // issue rows do). Parsed defensively: a non-numeric param opens the backlog, never NaN.
    const ticketParam = params.get('ticket');
    const initialTicket = ticketParam && /^\d+$/.test(ticketParam) ? Number(ticketParam) : null;
    // The masthead's three always-on modes: delivery (the line), maintenance (the
    // ticket loop), and promotion (where proven releases go beyond the entry
    // environment). ?mode=<name> deep-links the tab (the fleet inbox does).
    const [cockpitMode, setCockpitMode] = useState<'delivery' | 'maintenance' | 'promotion'>(
        params.get('mode') === 'maintenance'
            ? 'maintenance'
            : params.get('mode') === 'promotion'
              ? 'promotion'
              : 'delivery',
    );

    const {
            current: currentSlot,
            overview: overviewSlot,
            overviewLoading: overviewLoadingSlot,
            overviewError,
            loadOverview,
            planNext,
            drive,
            sign,
            setDeliveryConfig,
            setDeliveryTimeout,
            reopen,
            closeLine,
            action,
            driveResult,
            actionLoading,
            actionError,
            clearAction,
            tree: treeSlot,
            treeLoading,
            loadTree,
            substanceError,
            recordError,
            treeError,
            fileError,
            openFile: openFileSlot,
            fileLoading,
            openRepoFile,
            references: referencesSlot,
            toggleReference,
            substance: substanceSlot,
            substanceLoading: substanceLoadingSlot,
            loadSubstance,
            record: recordSlot,
            loadRecord,
            openProject,
        } = useDeliveries(),
        { agents, loadAgents, applyAgentToDelivery, saveAgent } = useAgents(),
        { chatConfigured, chatModel, sendChat, clearChat } = useCopilot(),
        {
            runs,
            loadRuns,
            runGraph: runGraphSlot,
            loadRunGraph,
            bandGraphs,
            loadBandGraph,
            nodeLogs,
            loadNodeLogs,
            runLogs: runLogsSlot,
            runLogsLoading,
            loadRunLogs,
            stopRun,
            resumeRun,
        } = useRuns(),
        { fleet, loadFleet } = useFleet(),
        { session, loadSession } = useSettings();

    // The store's per-project slots are single, so between the render that sees a new ?repo=
    // and the effect that opens it they still hold the PREVIOUS project. Read them only while
    // the store is stamped with this repo; until then the page reads as loading rather than
    // painting the project the operator just left (issue #60). Everything derived below - the
    // line, the panes, the worktree, the co-pilot's references - flows from these, so gating
    // them here is the whole guard.
    const opened = useDeliveries((s) => s.viewedRepo) === repo;
    const overview = opened ? overviewSlot : null;
    const current = opened ? currentSlot : null;
    const overviewLoading = opened ? overviewLoadingSlot : true;
    const substance = opened ? substanceSlot : null;
    const substanceLoading = opened ? substanceLoadingSlot : true;
    const record = opened ? recordSlot : null;
    const tree = opened ? treeSlot : EMPTY_TREE;
    const openFile = opened ? openFileSlot : null;
    const references = opened ? referencesSlot : EMPTY_REFS;
    const runGraph = opened ? runGraphSlot : null;
    const runLogs = opened ? runLogsSlot : null;

    // The co-pilot thread is scoped to this repo's DELIVERY mode - a maintenance thread, or
    // another repo's, never renders here (each is a distinct key in the store).
    const chat = useCopilot((s) => s.chats[chatKey(repo, 'delivery')] ?? EMPTY_CHAT);
    const chatBusy = useCopilot((s) => Boolean(s.chatBusyKeys[chatKey(repo, 'delivery')]));

    const [selected, setSelected] = useState<string | null>(null);
    const [showLogs, setShowLogs] = useState(false);
    // The run's job strip is executor plumbing; the LINE is the cockpit's truth. Folded
    // until the operator asks - the run pill still tells the state at a glance.
    const [bandOpen, setBandOpen] = useState(false);
    const [buildTab, setBuildTab] = useState<BuildTab>('worktree');
    const [showStart, setShowStart] = useState(false);
    // "Switch to Delivery" (issue #13): the prepared prompt from an over-scope maintenance ticket,
    // pre-filled into the establish form. The nonce remounts the form (a changing key) so a new
    // switch re-seeds its request field even if the form was already on screen.
    const [deliveryPrefill, setDeliveryPrefill] = useState('');
    const [switchNonce, setSwitchNonce] = useState(0);
    // The gate review's second outcome: Re-drive opens a composer for the feedback that
    // steers the revision. The co-pilot's staged ```redrive block pre-fills it.
    const [redriveOpen, setRedriveOpen] = useState(false);
    const [redriveNote, setRedriveNote] = useState('');
    // The composer's target phase: set by whichever surface opened it (the gate card, or a
    // selected phase's header), so the act always names what it re-drives.
    const [redriveTarget, setRedriveTarget] = useState<string | null>(null);
    // Which act is in flight, for honest button labels: actionLoading disables every
    // control, but only the pressed one may claim to be working.
    const [busyAct, setBusyAct] = useState<'sign' | 'redrive' | null>(null);
    // Below lg the workspace and the console can't sit side by side, so a tab picks which
    // one shows; at lg both render in the grid and this is inert (the PaneToggle is hidden).
    const [pane, setPane] = useState<'work' | 'console'>('work');

    // Opening the composer is the ENTIRE visible effect of pressing any Re-drive control,
    // and the composer lives in the console - a card that sits a screen below the line on
    // a tall page (a degraded line, its run band unfolded) and is not rendered at all below
    // lg while the workspace pane holds the tab. So the controls in the line card fired
    // into a panel the operator could not see, which reads exactly like a dead button. Every
    // surface opens it through here: the console pane is selected, so the composer is
    // rendered at every width, and the effect below carries the operator to it.
    const redriveRef = useRef<HTMLTextAreaElement | null>(null);
    const openRedrive = useCallback((phase: string | null) => {
        setRedriveTarget(phase);
        setRedriveOpen(true);
        setPane('console');
    }, []);
    useEffect(() => {
        if (!redriveOpen) return;
        const el = redriveRef.current;
        if (!el) return;
        // The composer mounts in this same commit, so the node is here to scroll to. Focus
        // without a second scroll - scrollIntoView is already taking us there.
        el.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
        el.focus({ preventScroll: true });
    }, [redriveOpen]);

    const name = repo ? repoName(repo) : '';
    const slug = name.toLowerCase().replace(/[^a-z0-9-]/g, '-');
    const domain = window.location.hostname.split('.').slice(1).join('.');

    // Reset the per-delivery view state when the repo changes - during render (React's
    // "adjust state on a prop change" pattern), not in an effect, so it neither trips the
    // effect-setState lint nor costs a render-then-reset extra pass.
    const [viewedRepo, setViewedRepo] = useState(repo);
    if (repo !== viewedRepo) {
        setViewedRepo(repo);
        setSelected(null);
        setShowLogs(false);
        setBandOpen(false);
        setBuildTab('worktree');
        setShowStart(false);
        setRedriveOpen(false);
        setRedriveNote('');
        setBusyAct(null);
        setPane('work');
        setCockpitMode(params.get('mode') === 'maintenance' ? 'maintenance' : 'delivery');
    }

    useEffect(() => {
        void loadSession().catch(() => undefined);
    }, [loadSession]);

    useEffect(() => {
        void loadAgents();
        if (repo) {
            // Retire the previous project's panes and stamp this one BEFORE any fetch, so
            // every response below is admitted only while this project is still open.
            openProject(repo);
            void loadOverview(repo);
            void loadRuns();
        }
    }, [repo, loadOverview, loadRuns, openProject, loadAgents]);

    // This delivery's newest run is the live one: the line overlays it, the controls act on it.
    const mine = useMemo(
        () => runs.filter((run) => run.repo === repo && run.kind === 'delivery'),
        [runs, repo],
    );
    const activeRun = mine[0] ?? null;
    const activeHandle = activeRun?.handle ?? null;

    useEffect(() => {
        if (activeHandle) void loadRunGraph(activeHandle);
    }, [activeHandle, loadRunGraph]);

    // The cockpit is live: while the newest run executes, poll the executor and re-derive
    // the line, so the page moves on its own instead of asking for manual refreshes.
    useEffect(() => {
        const ph = runGraph?.phase ?? activeRun?.phase;
        if (!activeHandle || runEnded(ph)) return;
        const t = setInterval(() => {
            void loadRuns();
            void loadRunGraph(activeHandle);
            void loadOverview(repo);
        }, 15000);
        return () => clearInterval(t);
    }, [
        activeHandle,
        runGraph?.phase,
        activeRun?.phase,
        repo,
        loadRuns,
        loadRunGraph,
        loadOverview,
    ]);

    // A repo with no open line is not an error page: it is a LIVE (or bare) project whose
    // cockpit still serves - worktree, live app, co-pilot - and the place to open a new line.
    // Delivery is an always-on mode, not a one-way graduation.
    const isLiveProject = current?.status === 'not-a-delivery';
    useEffect(() => {
        if (isLiveProject && fleet.length === 0) void loadFleet();
    }, [isLiveProject, fleet.length, loadFleet]);
    const fleetItem = fleet.find((p) => p.repo === repo) ?? null;
    // The app's own identity, when this repo joined one. The delivery slug is the
    // REPOSITORY's, and everything below that addresses the platform - the live host, the
    // docs path - is named for the app, so composing them from the slug pointed at hosts
    // and paths that do not exist wherever the two differ. Falls back to the slug, which
    // is correct wherever they coincide.
    const appSlug = fleetItem?.app_name || slug;
    const liveHost = fleetItem?.host || `${appSlug}.${domain}`;

    const pendingGate = current ? selectPendingGate(current) : null;
    const phases = overview?.phases ?? [];
    const selectedPhase =
        phases.find((p) => p.name === selected) ??
        phases.find((p) => p.is_current) ??
        phases[0] ??
        null;
    const here = selectedPhase?.name ?? current?.phase ?? '';
    const [contentRequestKey, setContentRequestKey] = useState<string | null>(null);
    const phaseContentKey = `${repo}::${selectedPhase?.name ?? ''}`;
    const requestPhaseContent = (name: string) => {
        setSelected(name);
        setContentRequestKey(`${repo}::${name}`);
    };

    const selectedPhaseName = selectedPhase?.name;
    const selectedRecordPath =
        selectedPhase && (selectedPhase.record_present || selectedPhase.renderer === 'learn')
            ? selectedPhase.record
            : null;
    useEffect(() => {
        if (
            repo &&
            selectedPhaseName &&
            !isLiveProject &&
            contentRequestKey === `${repo}::${selectedPhaseName}`
        ) {
            void loadSubstance(repo, selectedPhaseName);
            void loadRecord(repo, selectedRecordPath);
        }
    }, [
        repo,
        selectedPhaseName,
        selectedRecordPath,
        isLiveProject,
        contentRequestKey,
        loadSubstance,
        loadRecord,
    ]);

    // Logs are LIVE: while the pane is open and the run executes, tail the executor and
    // stay glued to the bottom. Scrolling up PAUSES the refresh entirely (a moving tail
    // yanks the text out from under the reader); scrolling back down, or the resume
    // chip, follows again.
    const logsRef = useRef<HTMLPreElement | null>(null);
    const [logsFollowing, setLogsFollowing] = useState(true);
    useEffect(() => {
        if (!showLogs || !activeHandle || !logsFollowing) return;
        const ph = runGraph?.phase ?? activeRun?.phase;
        if (runEnded(ph)) return;
        const t = setInterval(() => void loadRunLogs(activeHandle), 4000);
        return () => clearInterval(t);
    }, [showLogs, activeHandle, logsFollowing, runGraph?.phase, activeRun?.phase, loadRunLogs]);
    useEffect(() => {
        const el = logsRef.current;
        if (el && logsFollowing) el.scrollTop = el.scrollHeight;
    }, [runLogs, showLogs, logsFollowing]);

    async function drivePhase(from?: string, feedback?: string) {
        await drive({
            target: repo,
            config: { worker_credential: null, repo_target: repo },
            from_phase: from ?? null,
            feedback: feedback ?? null,
        });
        void loadRuns();
    }

    // Fire the gate review's reject-with-reasons: journal + re-drive as one act. The
    // composer survives a failed submit (the note is the operator's words - keep them).
    async function fireRedrive() {
        await drivePhase(
            redriveTarget ?? current?.phase ?? undefined,
            redriveNote.trim() || undefined,
        );
        if (!useDeliveries.getState().actionError) {
            setRedriveOpen(false);
            setRedriveNote('');
            setRedriveTarget(null);
        }
    }

    async function planNextPhase() {
        await planNext({
            target: repo,
            config: { worker_credential: null, repo_target: repo },
        });
    }

    // Close the line: tag the scratch ref delivered/<slug>/P<n>, then remove it (no release,
    // no default-branch commit). Confirmed once, from wherever the operator presses it - the
    // always-on control or the delivered-line primary.
    function confirmClose() {
        if (
            window.confirm(
                `Close this line?\n\nThis tags ${current?.repo}'s scratch ref delivered/<slug>/P<n> and removes the ref, ending the delivery. Every record stays reachable through the tag; the repo, its code, and everything the studios hold are untouched.`,
            )
        )
            void closeLine(repo);
    }

    if (!repo) {
        return (
            <Cockpit>
                <Card className="p-6 text-sm text-muted-foreground">
                    No delivery selected.{' '}
                    <Link to="/" className="text-link hover:underline">
                        Back to the fleet
                    </Link>
                    .
                </Card>
            </Cockpit>
        );
    }

    // A deliberate close is not a failure - say "stopped", in amber, not red. The Console's
    // own mark (`stop`, and the `Stopped` phase derived from it) is the authority, because it
    // is written by the same act that requests the shutdown and names WHO stopped the run.
    // The executor's message stays a fallback for the one case the mark cannot cover: a run
    // stopped before this shipped, or by a hand reaching past the Console's controls.
    const wasStopped = Boolean(
        runGraph?.stop ||
        runGraph?.phase === 'Stopped' ||
        // nodes may be absent on a degraded executor read; absent is not stopped
        runGraph?.nodes?.some((n) => n.message?.includes('Stopped with strategy')),
    );
    const stopTitle =
        runGraph?.stop === 'superseded'
            ? 'Stopped by the Console when a newer drive took over - not a failure'
            : 'Stopped by the operator - not a failure';
    // A failed run says why beside its pill: the worker's last refusal line (#181).
    const refusal = wasStopped ? null : lastRefusal(runGraph);
    const controls = overview?.controls;
    // Sign releases a run only where one is parked on the gate or still heading there. On a
    // line whose run has ended (a one-shot stamp that refused, a stopped run) Sign closes the
    // gate and a drive takes the line on.
    const signReleasesRun = controls?.run_in_flight ?? false;
    const redriveInFlight = controls?.redrive_in_flight ?? false;
    const primaryKind = controls?.primary_kind ?? 'unavailable';
    const isLearned = controls?.is_learned ?? false;
    const closeIsNext = controls?.close_is_next ?? false;
    const selectedHasRun = selectedPhase
        ? (controls?.phase_has_run[selectedPhase.name] ?? false)
        : false;
    const buildArtifact = phases.find((p) => p.renderer === 'build')?.artifact ?? null;
    const liveUrl = buildArtifact?.exists ? `https://${liveHost}` : null;
    // The onboarding PR the build phase opened, recorded in build.md frontmatter
    // (onboarding_pr:). Surfaced at the delivery gate so the operator can merge it - or see
    // it is still pending - without hand-querying platform-studio for it.
    const onboardingPr =
        selectedPhase?.renderer === 'build'
            ? (record?.content?.match(/^onboarding[_-]?pr:\s*(\S+)/im)?.[1] ?? null)
            : null;

    // The page's controls live in the masthead: identity + status left, the delivery-wide
    // dials right. A second header row below the masthead wastes a line of height.
    const bar = current ? (
        <>
            <div className="min-w-0">
                <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
                    {name}
                    {isLiveProject ? (
                        <span className="rounded-full border border-[hsl(var(--success))]/40 bg-[hsl(var(--success))]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[hsl(var(--success))]">
                            {fleetItem?.onboarded ? 'live · no open line' : 'no open line'}
                        </span>
                    ) : redriveInFlight ? (
                        // Degraded, but a run is live: the committed record still reads
                        // status: degraded (the condition above), yet a run is in flight, so the
                        // masthead agrees with the run strip instead of flashing a red "Degraded"
                        // the run contradicts. Not always an operator's re-drive - in one-shot a
                        // phase that reaches a gate counts as a failed attempt and is retried, so
                        // this is what an ordinary automatic retry looks like from the masthead.
                        <span className="rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-400">
                            Re-driving
                        </span>
                    ) : (
                        <span className="inline-flex items-center gap-2">
                            <SeedBadge seed={current.seed ?? ''} demoOf={current.demo_of} />
                            <StatusBadge status={current.status} label={current.status_label} />
                        </span>
                    )}
                </span>
                <a
                    href={`https://github.com/${current.repo}`}
                    target="_blank"
                    rel="noreferrer"
                    title={current.repo}
                    className="block w-0 min-w-full truncate font-mono text-[10px] text-muted-foreground hover:text-link"
                >
                    {current.repo} ↗
                </a>
            </div>
            <span className="flex-1" />
            <div
                className="flex gap-0.5 rounded-full border border-border bg-well/30 p-0.5"
                title="A project runs both modes at will - delivery for 0→1 and majors, maintenance for tickets."
            >
                <button
                    type="button"
                    onClick={() => setCockpitMode('delivery')}
                    className={cn(
                        'rounded-full px-3 py-1.5 text-[11px] font-semibold',
                        cockpitMode === 'delivery'
                            ? 'bg-secondary text-secondary-foreground'
                            : 'text-muted-foreground hover:text-foreground',
                    )}
                >
                    Delivery
                </button>
                <button
                    type="button"
                    onClick={() => setCockpitMode('maintenance')}
                    title="The ticket loop: one line per ticket - resolve, review, merge - picked from the backlog."
                    className={cn(
                        'rounded-full px-3 py-1.5 text-[11px] font-semibold',
                        cockpitMode === 'maintenance'
                            ? 'bg-secondary text-secondary-foreground'
                            : 'text-muted-foreground hover:text-foreground',
                    )}
                >
                    Maintenance
                </button>
                <button
                    type="button"
                    onClick={() => setCockpitMode('promotion')}
                    title="Where a proven release goes beyond the entry environment: one row per target the app's contract declares."
                    className={cn(
                        'rounded-full px-3 py-1.5 text-[11px] font-semibold',
                        cockpitMode === 'promotion'
                            ? 'bg-secondary text-secondary-foreground'
                            : 'text-muted-foreground hover:text-foreground',
                    )}
                >
                    Promotion
                </button>
            </div>
            {/* The provider + model picker renders for EVERY project, not only open deliveries:
                a maintenance-only repo needs to pick the provider its resolve/review workers and
                its co-pilot run on, and seating it is now git-free (Console-local selection +
                per-slug credential), so it never fabricates a .delivery/ (issue #4 / R72). */}
            {overview && (
                <DeliveryModelForm
                    config={overview.config}
                    agents={agents}
                    caller={callerOf(session)}
                    disabled={actionLoading}
                    error={actionError}
                    onApplyAgent={(n, m) => void applyAgentToDelivery(repo, n, m)}
                    onSaveAgent={(n, b, m, c, level, team) => {
                        void (async () => {
                            if (await saveAgent(n, 'claude', b, m, c, m ? [m] : [], level, team)) {
                                await applyAgentToDelivery(repo, n, m || undefined);
                            }
                        })();
                    }}
                    onSetTimeout={(h) => void setDeliveryTimeout(repo, h)}
                />
            )}
        </>
    ) : undefined;

    const phaseRenderers: Record<string, React.ReactNode> = {
        scope: (
            <ScopePane
                substance={substanceLoading ? null : substance}
                record={record?.content ?? null}
                slug={repo ? (repo.split(/[\\/]/).filter(Boolean).pop() ?? null) : null}
            />
        ),
        design: (
            <DesignPane
                substance={substanceLoading ? null : substance}
                record={record?.content ?? null}
            />
        ),
        intent: substance?.claims?.length ? (
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto pr-1 [&>*]:flex-none">
                <div className="rounded-lg border border-border">
                    {substance.claims.map((c) => (
                        <div
                            key={c.id}
                            className="flex flex-wrap items-baseline gap-3 border-b border-border px-3.5 py-2.5 text-xs last:border-b-0"
                        >
                            <span className="w-28 flex-none font-mono text-[11px] font-semibold text-link">
                                {c.id}
                            </span>
                            <span className="min-w-0 basis-full whitespace-pre-wrap break-words leading-relaxed sm:basis-auto sm:flex-1">
                                {c.statement}
                            </span>
                            {c.criticality && (
                                <span className="flex-none font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                                    {c.criticality}
                                </span>
                            )}
                            <span
                                className={cn(
                                    'flex-none font-mono text-[10px]',
                                    c.status === 'active'
                                        ? 'text-[hsl(var(--success))]'
                                        : 'text-muted-foreground',
                                )}
                            >
                                {c.status || '-'}
                            </span>
                        </div>
                    ))}
                </div>
                {record?.content && (
                    <details className="rounded-lg border border-border bg-well/10">
                        <summary className="cursor-pointer px-3.5 py-2.5 font-mono text-[11px] font-semibold text-muted-foreground">
                            handoff.md - the pinned build plan
                        </summary>
                        <div className="border-t border-border p-4">
                            <RecordDocument text={record.content} />
                        </div>
                    </details>
                )}
            </div>
        ) : record?.content ? (
            <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-well/10 p-4">
                <RecordDocument text={record.content} />
            </div>
        ) : (
            <EmptyPane>
                Turns the scope into attestable intents and a pinned build plan (CSD, applied
                locally - no studio). The claims land here, as a table, when its worker runs.
            </EmptyPane>
        ),
        build: (
            <div className="flex min-h-0 flex-1 flex-col gap-2">
                <div className="flex flex-none gap-1">
                    {(['worktree', 'live', 'evidence'] as BuildTab[]).map((t) => (
                        <button
                            key={t}
                            type="button"
                            onClick={() => setBuildTab(t)}
                            className={cn(
                                'rounded-md px-2.5 py-1.5 font-mono text-[11px] font-semibold capitalize transition-colors',
                                buildTab === t
                                    ? 'bg-secondary text-secondary-foreground'
                                    : 'text-muted-foreground hover:text-foreground',
                            )}
                        >
                            {t === 'live' ? 'Live app' : t}
                        </button>
                    ))}
                </div>
                {buildTab === 'worktree' && (
                    <div className="min-h-0 flex-1">
                        <WorktreePanel
                            repo={repo}
                            tree={tree}
                            treeLoading={treeLoading}
                            onLoadTree={loadTree}
                            error={treeError || fileError}
                            openFile={openFile}
                            fileLoading={fileLoading}
                            onOpenFile={openRepoFile}
                            references={references}
                            onToggleReference={toggleReference}
                        />
                    </div>
                )}
                {buildTab === 'live' &&
                    (liveUrl ? (
                        <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-white">
                            <iframe title="live app" src={liveUrl} className="h-full w-full" />
                        </div>
                    ) : (
                        <EmptyPane>
                            Nothing shipped yet - the live app embeds here once build+ship lands it
                            on the platform.
                            {onboardingPr && (
                                <>
                                    {' '}
                                    Onboarding PR awaiting merge:{' '}
                                    <a
                                        href={onboardingPr}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-link hover:underline"
                                    >
                                        {onboardingPr} ↗
                                    </a>
                                </>
                            )}
                        </EmptyPane>
                    ))}
                {buildTab === 'evidence' && (
                    <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-well/10 p-4">
                        {record?.content ? (
                            <RecordDocument text={record.content} />
                        ) : (
                            <p className="text-xs text-muted-foreground">
                                The evidence chain (CI · registry artifacts · GitOps health · the
                                public probe) lands in build.md when this phase runs.
                            </p>
                        )}
                    </div>
                )}
            </div>
        ),
        learn: record?.content ? (
            <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-well/10 p-4">
                <RecordDocument text={record.content} />
            </div>
        ) : (
            <EmptyPane>
                Runs after delivery: re-verifies the claims and durable homes, files the surviving
                lessons and recommendations as learn-titled tickets for the maintenance loop to
                review and land, journals what it did here, and stamps learned: into this journal's
                frontmatter so the line reads Learned. Driven from the console it leaves the scratch
                in place - closing it (the tag, then removing the scratch ref) is the separate
                Close-line act on the line card - so an unattended run never destroys the journal it
                just wrote.
            </EmptyPane>
        ),
    };
    return (
        <Cockpit frame bar={bar}>
            {overviewError && (
                <div className="flex-none rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {overviewError}
                </div>
            )}
            {overviewLoading && !current && (
                <p className="text-sm text-muted-foreground">Loading delivery…</p>
            )}

            {/* On desktop the masthead bar carries the delivery's identity; below lg that bar
                collapses behind the Controls disclosure, so this strip keeps "which delivery
                am I on" visible. lg:hidden keeps it off the desktop cockpit. */}
            {current && (
                <div className="flex flex-none flex-wrap items-baseline gap-x-2 gap-y-1 lg:hidden">
                    <span className="text-sm font-semibold tracking-tight">{name}</span>
                    <a
                        href={`https://github.com/${current.repo}`}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-[10px] text-muted-foreground hover:text-link"
                    >
                        {current.repo} ↗
                    </a>
                </div>
            )}

            {/* The project cockpit for a repo with NO open line: live app + worktree + co-pilot,
                and the act that matters - opening the next line. The line card would lie here
                (no records to derive from), so it does not render. */}
            {/* The Maintenance tab: the OTHER always-on mode, one toggle away for every
                repo - mid-delivery, live, or bare. It replaces the delivery content;
                the masthead (identity + toggle + dials) stays. */}
            {current && cockpitMode === 'promotion' && <PromotionPane repo={repo} />}

            {current && cockpitMode === 'maintenance' && (
                <MaintenancePane
                    repo={repo}
                    initialTicket={initialTicket}
                    // The switch is offered only when this repo has no open delivery line (the guard).
                    onSwitchToDelivery={(prompt) => {
                        // Flip to the Delivery view and open the establish form, pre-filled with the
                        // prepared prompt; the operator then opens the line via the existing action.
                        setDeliveryPrefill(prompt);
                        setSwitchNonce((n) => n + 1);
                        setCockpitMode('delivery');
                        setShowStart(true);
                    }}
                />
            )}

            {current && cockpitMode === 'delivery' && isLiveProject && (
                <>
                    <Card className="flex-none p-4">
                        <div className="flex flex-wrap items-center gap-3">
                            <div className="min-w-0 flex-1">
                                <p className="text-sm font-semibold">
                                    {fleetItem?.onboarded
                                        ? 'Live on the platform · no open delivery line'
                                        : 'No open delivery line'}
                                </p>
                                <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
                                    {fleetItem?.onboarded
                                        ? 'A reconciled, closed line (its records live on the delivered/<slug> tag), or an app from before the foundry. '
                                        : 'A plain repo with no delivery scratch. '}
                                    Delivery and maintenance are always-on modes: open a new line
                                    any time for the next major, adopting the work the studios
                                    already hold.
                                </p>
                            </div>
                            {fleetItem?.onboarded && (
                                <a
                                    href={
                                        projectLinks(slug, fleetItem?.app_name, fleetItem?.host)
                                            .docs
                                    }
                                    target="_blank"
                                    rel="noreferrer"
                                    className="rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:border-link/50 hover:text-link"
                                >
                                    docs ↗
                                </a>
                            )}
                            <Button type="button" onClick={() => setShowStart((s) => !s)}>
                                {showStart ? 'Close' : 'Open a new line'}
                            </Button>
                        </div>
                        {showStart && (
                            <div className="mt-4">
                                <StartDeliveryForm
                                    key={`start-${switchNonce}`}
                                    initialTarget={name}
                                    initialRequest={deliveryPrefill}
                                    onStarted={() => {
                                        setShowStart(false);
                                        setDeliveryPrefill('');
                                        void loadOverview(repo);
                                        void loadFleet();
                                    }}
                                />
                            </div>
                        )}
                    </Card>

                    <PaneToggle
                        options={[
                            { key: 'work', label: 'Worktree' },
                            { key: 'console', label: 'Co-pilot' },
                        ]}
                        active={pane}
                        onSelect={(k) => setPane(k as 'work' | 'console')}
                    />
                    <div className="grid min-h-[560px] flex-1 grid-cols-1 gap-3 lg:min-h-[calc(100dvh-220px)] lg:grid-cols-[minmax(0,1fr)_400px]">
                        <Card
                            className={cn(
                                'min-h-0 min-w-0 flex-col gap-3 p-4',
                                pane === 'work' ? 'flex' : 'hidden lg:flex',
                            )}
                        >
                            <div className="flex flex-none gap-1">
                                {(['worktree', 'live'] as BuildTab[]).map((t) => (
                                    <button
                                        key={t}
                                        type="button"
                                        onClick={() => setBuildTab(t)}
                                        className={cn(
                                            'rounded-md px-2.5 py-1.5 font-mono text-[11px] font-semibold capitalize transition-colors',
                                            buildTab === t
                                                ? 'bg-secondary text-secondary-foreground'
                                                : 'text-muted-foreground hover:text-foreground',
                                        )}
                                    >
                                        {t === 'live' ? 'Live app' : t}
                                    </button>
                                ))}
                            </div>
                            {buildTab !== 'live' && (
                                <div className="min-h-0 flex-1">
                                    <WorktreePanel
                                        repo={repo}
                                        tree={tree}
                                        treeLoading={treeLoading}
                                        onLoadTree={loadTree}
                                        error={treeError || fileError}
                                        openFile={openFile}
                                        fileLoading={fileLoading}
                                        onOpenFile={openRepoFile}
                                        references={references}
                                        onToggleReference={toggleReference}
                                    />
                                </div>
                            )}
                            {buildTab === 'live' &&
                                (fleetItem?.onboarded ? (
                                    <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-white">
                                        <iframe
                                            title="live app"
                                            src={`https://${liveHost}`}
                                            className="h-full w-full"
                                        />
                                    </div>
                                ) : (
                                    <EmptyPane>
                                        Not on the platform yet - the live app embeds here once a
                                        line ships it.
                                    </EmptyPane>
                                ))}
                        </Card>

                        <Card
                            className={cn(
                                'min-h-0 flex-col p-0',
                                pane === 'console' ? 'flex' : 'hidden lg:flex',
                            )}
                        >
                            <div className="flex flex-none flex-wrap items-center gap-1.5 border-b border-border px-3.5 py-2.5">
                                <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1 font-mono text-[10px] text-muted-foreground">
                                    <span className="h-1 w-1 rounded-full bg-[hsl(var(--success))]" />
                                    {current.repo}
                                </span>
                            </div>
                            <div className="min-h-0 flex-1 p-3.5">
                                <CoPilotPanel
                                    messages={chat}
                                    busy={chatBusy}
                                    configured={chatConfigured}
                                    model={chatModel}
                                    references={references}
                                    onSend={(m) => void sendChat(repo, '', m)}
                                    onClear={() => clearChat(repo, 'delivery')}
                                    onToggleReference={toggleReference}
                                    notConfiguredHint={
                                        <>
                                            This project has no provider of its own; the co-pilot
                                            falls back to the home driver. Pick a saved provider
                                            under{' '}
                                            <Link
                                                to="/settings"
                                                className="text-link hover:underline"
                                            >
                                                Settings
                                            </Link>{' '}
                                            · Home co-pilot.
                                        </>
                                    }
                                    emptyHint="Ask about this project - reference files from the worktree and they ride along."
                                />
                            </div>
                        </Card>
                    </div>
                </>
            )}

            {current && cockpitMode === 'delivery' && !isLiveProject && (
                <>
                    {/* The line card: drive + the run's controls, the phase line, the run band. */}
                    <Card className="flex-none overflow-hidden">
                        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
                            {(() => {
                                // The top-left primary follows the live run so its verb always
                                // matches what pressing it does - never a plain "Drive" that
                                // would silently supersede a run in flight. It drives the CURRENT
                                // phase (Learn once delivered); closing the line is the separate
                                // always-on act beside it, never this button. Starting a NEW
                                // workflow from a specific phase lives on each phase's pane.
                                if (primaryKind === 'unavailable')
                                    return (
                                        <Button type="button" disabled>
                                            Observation unavailable
                                        </Button>
                                    );
                                if (primaryKind === 'running') {
                                    return (
                                        <Button
                                            type="button"
                                            disabled
                                            title="A run is in flight - Stop it first, or wait for its gate."
                                        >
                                            ⏳ Running…
                                        </Button>
                                    );
                                }
                                if (primaryKind === 'resume') {
                                    // The run is parked on a gate suspend, and the gate's act is
                                    // Sign (stamp + release in one breath) - so once the derived
                                    // state has caught up, the primary IS Sign. Until it catches
                                    // up (the derived state is a warm cache that can lag the
                                    // worker's push by a refresh tick), offer nothing clickable:
                                    // a live operator got funneled into a primary "Resume" here
                                    // and released an unsigned gate. The run band's Resume stays
                                    // the deliberate fallback for a signed-but-stuck run, and the
                                    // backend refuses an unsigned release either way.
                                    if (controls?.can_sign && pendingGate) {
                                        return (
                                            <Button
                                                type="button"
                                                onClick={async () => {
                                                    setBusyAct('sign');
                                                    try {
                                                        await sign(repo);
                                                    } finally {
                                                        setBusyAct(null);
                                                    }
                                                }}
                                                disabled={actionLoading}
                                                title={`Approve the ${pendingGate} gate: stamps today into the record and releases the next phase in the same act.`}
                                            >
                                                {busyAct === 'sign'
                                                    ? 'Signing…'
                                                    : `Sign the ${pendingGate} gate`}
                                            </Button>
                                        );
                                    }
                                    return (
                                        <Button
                                            type="button"
                                            disabled
                                            title="The run is parked on a gate and the derived line state is still catching up (a background refresh tick). The Sign action lands here on its own; if you already signed and the run stayed parked, Resume on the right releases it."
                                        >
                                            ⏸ Parked at gate - syncing…
                                        </Button>
                                    );
                                }
                                if (primaryKind === 'redrive') {
                                    return (
                                        <Button
                                            type="button"
                                            onClick={() => openRedrive(current?.phase ?? null)}
                                            disabled={actionLoading}
                                            title="The run failed - re-drive this phase (optionally with feedback)."
                                        >
                                            ↻ Re-drive
                                        </Button>
                                    );
                                }
                                // Learn already executed (the journal frontmatter carries its
                                // learned: stamp), so this button would re-drive a finished
                                // phase: say so in the verb rather than offering a plain Drive.
                                // The close is the contextual next act, but it stays in its own
                                // slot beside this one - it never takes the primary, because a
                                // primary it holds only in SOME states is a primary it vacates
                                // in others (see the Close button's own note).
                                return (
                                    <Button
                                        type="button"
                                        variant={closeIsNext ? 'outline' : 'default'}
                                        onClick={() => void drivePhase()}
                                        disabled={actionLoading}
                                        title={
                                            isLearned
                                                ? 'Learn already ran; re-driving it is an idempotent no-op unless the line changed.'
                                                : undefined
                                        }
                                    >
                                        {actionLoading
                                            ? 'Working…'
                                            : isLearned
                                              ? '↻ Re-drive Learn'
                                              : current?.phase === 'learn'
                                                ? '▶ Drive Learn'
                                                : '▶ Drive'}
                                    </Button>
                                );
                            })()}
                            {/* The run shape sits beside the act it paces. It governs delivery runs
                                only, so it lives on the line card rather than the masthead, which
                                it pushed onto a second row at a 1536px viewport (issue #132). */}
                            {overview && (
                                <DeliveryConfigStrip
                                    config={overview.config}
                                    disabled={actionLoading}
                                    onChange={(mode) => void setDeliveryConfig(repo, mode)}
                                />
                            )}
                            <RunButton
                                onClick={() => void planNextPhase()}
                                disabled={actionLoading}
                            >
                                Plan · dry run
                            </RunButton>
                            {/* Closing the line is an UNCONDITIONAL act - the operator may end a
                                delivery at any point and for any reason (skip Learn, finish after
                                it, abandon a line mid-flight, walk away from one whose run keeps
                                failing), so this slot holds Close in EVERY state and is never
                                swapped out for another control. It was swapped once: a learned
                                line moved the close into the primary and put a Learn re-drive
                                here - which held only while the primary had nothing more urgent
                                to say. A learned line with a failed, running, or gate-parked run
                                gave the primary to that run and this slot to the re-drive, and
                                the close - the console's ONLY way to end a line - was reachable
                                nowhere (seen live on alexandria-main: learned, Build+Ship failed
                                x4). Emphasis is how a learned line points at the close now; a
                                slot it can be evicted from is not. That emphasis is the FILL
                                once nothing is in flight (closeIsNext): a red border beside a
                                filled primary is not a point, it is a footnote. */}
                            <RunButton
                                onClick={confirmClose}
                                disabled={actionLoading}
                                danger
                                className={cn(
                                    isLearned && 'border-destructive/60 text-destructive',
                                    closeIsNext &&
                                        'border-destructive bg-destructive text-destructive-foreground hover:border-destructive hover:bg-destructive/90 hover:text-destructive-foreground',
                                )}
                                title={
                                    isLearned
                                        ? `Learn ran${current.learned_on ? ` on ${current.learned_on}` : ''}; its lessons are filed. Close the line: tag the scratch ref delivered/<slug>/P<n>, then remove it (no release). The records stay reachable through the tag; the repo and studio artifacts are untouched.`
                                        : 'Close the line: tag the scratch ref delivered/<slug>/P<n>, then remove it (no release). The records stay reachable through the tag; the repo and studio artifacts are untouched.'
                                }
                            >
                                ⌫ Close line
                            </RunButton>
                            {activeHandle && (
                                <div className="ml-auto flex flex-wrap items-center gap-2">
                                    <span className="font-mono text-[11px] text-muted-foreground">
                                        run {activeRun?.name.split('-').slice(-1)[0]}
                                        {activeRun?.mode ? ` · ${activeRun.mode}` : ''}
                                    </span>
                                    <span
                                        className={cn(
                                            'rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold',
                                            runGraph?.phase === 'Succeeded'
                                                ? 'border-[hsl(var(--success))]/40 text-[hsl(var(--success))]'
                                                : wasStopped
                                                  ? 'border-amber-400/50 text-amber-400'
                                                  : runGraph?.phase === 'Failed' ||
                                                      runGraph?.phase === 'Error'
                                                    ? 'border-destructive/50 text-destructive'
                                                    : runGraph?.phase === 'Suspended'
                                                      ? 'border-amber-400/50 text-amber-400'
                                                      : 'border-link/50 text-link',
                                        )}
                                        title={wasStopped ? stopTitle : undefined}
                                    >
                                        {wasStopped &&
                                        (runGraph?.phase === 'Failed' ||
                                            runGraph?.phase === 'Stopped')
                                            ? 'stopped'
                                            : (runGraph?.phase ?? activeRun?.phase)}
                                    </span>
                                    {runGraph?.progress && (
                                        <span className="font-mono text-[10px] text-muted-foreground">
                                            {runGraph.progress}
                                        </span>
                                    )}
                                    {refusal && (
                                        <span
                                            className="max-w-md truncate font-mono text-[10.5px] text-destructive"
                                            title={refusal}
                                            data-testid="run-refusal"
                                        >
                                            {refusal}
                                        </span>
                                    )}
                                    <RunButton
                                        onClick={() => void resumeRun(activeHandle)}
                                        disabled={actionLoading}
                                        title="Release the parked suspend of a SIGNED gate - the fallback for a run that stayed parked after its sign. An unsigned gate refuses; Sign is the act that approves and releases."
                                    >
                                        Resume
                                    </RunButton>
                                    <RunButton
                                        onClick={() => void stopRun(activeHandle, false)}
                                        disabled={actionLoading}
                                        danger
                                    >
                                        Stop
                                    </RunButton>
                                    <RunButton
                                        onClick={() => void stopRun(activeHandle, true)}
                                        disabled={actionLoading}
                                        danger
                                    >
                                        Terminate
                                    </RunButton>
                                    <RunButton
                                        onClick={() => {
                                            const n = !showLogs;
                                            setShowLogs(n);
                                            if (n) {
                                                setLogsFollowing(true);
                                                void loadRunLogs(activeHandle);
                                            }
                                        }}
                                    >
                                        {showLogs ? 'Hide logs' : 'Logs'}
                                    </RunButton>
                                    <RunButton
                                        onClick={() => setBandOpen(!bandOpen)}
                                        title={
                                            bandOpen
                                                ? 'Hide the run band'
                                                : "Show the run band: this delivery's runs (current and superseded), each step clickable for its own logs"
                                        }
                                    >
                                        {bandOpen ? '⌃' : '⌄'}
                                    </RunButton>
                                </div>
                            )}
                        </div>

                        <div className="px-4 py-3">
                            <ObservationNotice
                                error={substanceError || recordError || treeError || fileError}
                            />
                            <ObservationNotice
                                freshness={overview?.freshness}
                                hasData={Boolean(overview)}
                            />
                            {phases.length > 0 ? (
                                <DeliveryLine
                                    phases={phases}
                                    selected={selectedPhase?.name ?? null}
                                    onSelect={requestPhaseContent}
                                />
                            ) : (
                                <p className="text-xs text-muted-foreground">
                                    No phases derived yet.
                                </p>
                            )}
                        </div>

                        {/* A degraded phase stopped without finishing (its record is
                            status: aborted). It is NOT done and NOT signable, so the gate
                            card below never renders for it - this red call-to-action is the
                            indication, and re-drive (after the operator clears the recorded
                            blocker) is the only way forward. While a re-drive is in flight it
                            is suppressed entirely: keeping it up would read as "the warning
                            won't go away and the button did nothing", and a second "re-driving"
                            banner would only echo what the primary button, the run pill, the
                            run strip, and the drive-submitted notice already say. The masthead
                            pill carries the re-driving state on its own. */}
                        {current.status === 'degraded' && !redriveInFlight && (
                            <div className="mx-4 mb-3 rounded-lg border border-destructive/50 bg-destructive/10 p-3">
                                <div className="flex items-baseline gap-2">
                                    <b className="text-sm capitalize">{current.phase} degraded</b>
                                    <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-destructive">
                                        stopped
                                    </span>
                                </div>
                                <p className="mb-2.5 mt-1 text-[11px] text-muted-foreground">
                                    This phase stopped without finishing (its record is{' '}
                                    <code className="rounded bg-well/30 px-1">status: aborted</code>
                                    ) - not done, and not signable. Open its record for the blocker,
                                    clear it, then re-drive. No gate is offered on a degraded phase.
                                </p>
                                <RunButton
                                    onClick={() => openRedrive(current.phase ?? null)}
                                    disabled={actionLoading}
                                    title="Re-run this phase once the recorded blocker is cleared"
                                    danger
                                >
                                    ↻ Re-drive <span className="capitalize">{current.phase}</span>
                                </RunButton>
                            </div>
                        )}

                        {runGraph && bandOpen && (
                            <RunBand
                                graph={runGraph}
                                runs={mine}
                                graphs={bandGraphs}
                                onUnfold={loadBandGraph}
                                nodeLogs={nodeLogs}
                                onNeedNodeLogs={loadNodeLogs}
                            />
                        )}

                        {showLogs && activeHandle && (
                            <div className="border-t border-border">
                                <div className="flex items-center justify-between bg-well/30 px-3 py-1">
                                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                                        run logs
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setLogsFollowing(true);
                                            void loadRunLogs(activeHandle);
                                        }}
                                        className={cn(
                                            'font-mono text-[10px]',
                                            logsFollowing
                                                ? 'text-[hsl(var(--success))]'
                                                : 'text-amber-400 hover:text-link',
                                        )}
                                        title={
                                            logsFollowing
                                                ? 'Glued to the tail; scroll up to pause and read'
                                                : 'Paused while you read - click, or scroll to the bottom, to follow again'
                                        }
                                    >
                                        {logsFollowing ? '● following' : 'paused · resume'}
                                    </button>
                                </div>
                                <pre
                                    ref={logsRef}
                                    onScroll={(e) => {
                                        const el = e.currentTarget;
                                        setLogsFollowing(
                                            el.scrollHeight - el.scrollTop - el.clientHeight < 48,
                                        );
                                    }}
                                    className="max-h-64 overflow-auto bg-well/40 p-3 text-[11px] leading-snug text-muted-foreground"
                                >
                                    {runLogs == null && runLogsLoading
                                        ? 'Loading logs…'
                                        : runLogs || 'No logs yet.'}
                                </pre>
                            </div>
                        )}
                        {(actionError || action || driveResult) && (
                            <div className="flex flex-col gap-2 border-t border-border px-4 py-3">
                                <div className="flex items-center justify-between">
                                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                                        {driveResult
                                            ? 'drive submitted'
                                            : action
                                              ? 'dry run'
                                              : 'action'}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={clearAction}
                                        className="rounded px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground hover:text-link"
                                        title="Dismiss this panel"
                                    >
                                        ✕ dismiss
                                    </button>
                                </div>
                                {actionError && (
                                    <p className="text-sm text-destructive">{actionError}</p>
                                )}
                                {action && (
                                    <ActionPanel
                                        action={action}
                                        signReleasesRun={signReleasesRun}
                                    />
                                )}
                                {driveResult && <DriveResultPanel result={driveResult} />}
                            </div>
                        )}
                    </Card>

                    {/* Workspace: the phase's substance (hero) + the console (always docked).
                        Sized to fill the viewport under the masthead + line card, but the page
                        may scroll - clipping substance to avoid scrolling starved it of height
                        and cut off the co-pilot's composer. */}
                    <PaneToggle
                        options={[
                            { key: 'work', label: 'Workspace' },
                            { key: 'console', label: 'Console' },
                        ]}
                        active={pane}
                        onSelect={(k) => setPane(k as 'work' | 'console')}
                    />
                    <div className="grid min-h-[560px] flex-1 grid-cols-1 gap-3 lg:min-h-[calc(100dvh-320px)] lg:grid-cols-[minmax(0,1fr)_400px]">
                        <Card
                            className={cn(
                                'min-h-0 min-w-0 flex-col gap-3 p-4',
                                pane === 'work' ? 'flex' : 'hidden lg:flex',
                            )}
                        >
                            {selectedPhase && (
                                <div className="flex flex-none flex-wrap items-center gap-2">
                                    <h2 className="text-sm font-semibold capitalize tracking-tight">
                                        {selectedPhase.name}
                                    </h2>
                                    <span className="text-[11px] text-muted-foreground">
                                        {selectedPhase.question}
                                    </span>
                                    <span className="ml-auto flex flex-wrap items-center gap-1.5">
                                        {selectedPhase.artifact?.exists &&
                                            selectedPhase.artifact.url && (
                                                <a
                                                    href={selectedPhase.artifact.url}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground hover:border-link/50 hover:text-link"
                                                    title={
                                                        selectedPhase.renderer === 'build'
                                                            ? 'The shipped app, live on the platform'
                                                            : `Open this delivery in ${selectedPhase.artifact.studio}`
                                                    }
                                                >
                                                    {/* The chip names its DESTINATION, not the studio behind it:
                                                    scope/design link to the studio's own project page, but
                                                    build+ship's link is the live app (platform-studio has no
                                                    per-app page), so labelling it "platform-studio" sent the
                                                    operator somewhere the name did not promise. */}
                                                    {selectedPhase.renderer === 'build'
                                                        ? 'live app'
                                                        : selectedPhase.artifact.studio}{' '}
                                                    ↗
                                                </a>
                                            )}
                                        {onboardingPr && (
                                            <a
                                                href={onboardingPr}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground hover:border-link/50 hover:text-link"
                                                title="The platform onboarding PR this build opened; merge it to admit the app"
                                            >
                                                onboarding PR ↗
                                            </a>
                                        )}
                                        <RunButton
                                            onClick={() => openRedrive(selectedPhase.name)}
                                            disabled={actionLoading}
                                            title="Re-run the line from this phase; optional feedback steers the revision, and any older run is superseded automatically"
                                        >
                                            {selectedHasRun ? '↻ Re-drive' : '▶ Drive'}{' '}
                                            <span className="capitalize">{selectedPhase.name}</span>
                                        </RunButton>
                                        {selectedPhase.gate_signed_on && (
                                            <RunButton
                                                onClick={() =>
                                                    void reopen(repo, selectedPhase.name)
                                                }
                                                disabled={actionLoading}
                                                title="Un-sign this gate and re-open the phase for work: its status returns to in-progress and this attempt's review is cleared. Downstream records are kept for review."
                                            >
                                                ⟲ Re-open
                                            </RunButton>
                                        )}
                                    </span>
                                </div>
                            )}

                            {contentRequestKey !== phaseContentKey ? (
                                <EmptyPane>
                                    <button
                                        type="button"
                                        onClick={() =>
                                            selectedPhase && requestPhaseContent(selectedPhase.name)
                                        }
                                        className="rounded-md border border-border px-3 py-2 text-link"
                                    >
                                        Load phase content
                                    </button>
                                </EmptyPane>
                            ) : (
                                (phaseRenderers[selectedPhase?.renderer ?? 'record'] ??
                                (record?.content ? (
                                    <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-well/10 p-4">
                                        <RecordDocument text={record.content} />
                                    </div>
                                ) : (
                                    <EmptyPane>No record available for this phase.</EmptyPane>
                                )))
                            )}
                        </Card>

                        {/* The console: what the co-pilot reads, the gate, the conversation. */}
                        <Card
                            className={cn(
                                'min-h-0 flex-col p-0',
                                pane === 'console' ? 'flex' : 'hidden lg:flex',
                            )}
                        >
                            <div className="flex flex-none flex-wrap items-center gap-1.5 border-b border-border px-3.5 py-2.5">
                                {selectedPhase?.record_present && selectedPhase.record && (
                                    <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1 font-mono text-[10px] text-muted-foreground">
                                        <span className="h-1 w-1 rounded-full bg-[hsl(var(--success))]" />
                                        {selectedPhase.record}
                                    </span>
                                )}
                                {activeRun && (
                                    <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1 font-mono text-[10px] text-muted-foreground">
                                        <span className="h-1 w-1 rounded-full bg-[hsl(var(--success))]" />
                                        run {activeRun.name.split('-').slice(-1)[0]}
                                    </span>
                                )}
                                {selectedPhase?.artifact?.exists && (
                                    <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1 font-mono text-[10px] text-muted-foreground">
                                        <span className="h-1 w-1 rounded-full bg-[hsl(var(--success))]" />
                                        {selectedPhase.artifact.studio}
                                    </span>
                                )}
                            </div>

                            {/* The rail is contextual to the SELECTED phase: this card is the gate's
                                decision point, so it renders only on the phase whose gate awaits. The
                                top strip already shows where the line is parked. */}
                            {current.status === 'awaiting-gate' &&
                                pendingGate &&
                                selectedPhase?.gate === pendingGate && (
                                    <div className="mx-3.5 mt-3 flex-none rounded-lg border border-link/50 bg-primary/10 p-3">
                                        <div className="flex items-baseline gap-2">
                                            <b className="text-sm capitalize">{pendingGate} gate</b>
                                            <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-link">
                                                awaiting
                                            </span>
                                        </div>
                                        <p
                                            className="mb-2.5 mt-1 text-[11px] text-muted-foreground"
                                            data-testid="gate-card-hint"
                                        >
                                            {signReleasesRun
                                                ? 'This phase is done and waits for your review. Signing stamps today into the record and releases the next phase; re-driving re-runs this phase with your feedback.'
                                                : 'This phase is done and waits for your review. Signing stamps today into the record and closes the gate; then drive the line on. Re-driving re-runs this phase with your feedback.'}
                                        </p>
                                        <div className="flex gap-2">
                                            <Button
                                                type="button"
                                                className="h-8 flex-1 text-xs"
                                                onClick={async () => {
                                                    setBusyAct('sign');
                                                    try {
                                                        await sign(repo);
                                                    } finally {
                                                        setBusyAct(null);
                                                    }
                                                }}
                                                disabled={actionLoading}
                                            >
                                                {busyAct === 'sign'
                                                    ? 'Signing…'
                                                    : `Sign the ${pendingGate} gate`}
                                            </Button>
                                            <Button
                                                type="button"
                                                variant="outline"
                                                className="h-8 text-xs"
                                                disabled={actionLoading}
                                                title="Reject this record and re-run the phase as a revision, steered by your feedback"
                                                onClick={() =>
                                                    openRedrive(selectedPhase?.name ?? null)
                                                }
                                            >
                                                Re-drive
                                            </Button>
                                        </div>
                                    </div>
                                )}

                            {redriveOpen && (
                                <div className="border-b border-border bg-well/10 px-3.5 py-3">
                                    <div className="flex items-baseline justify-between">
                                        <b className="text-sm">
                                            Re-drive ·{' '}
                                            <span className="capitalize">
                                                {redriveTarget ?? current.phase}
                                            </span>
                                        </b>
                                        <button
                                            type="button"
                                            className="font-mono text-[11px] text-muted-foreground hover:text-foreground"
                                            onClick={() => setRedriveOpen(false)}
                                        >
                                            ✕
                                        </button>
                                    </div>
                                    <p className="mb-1.5 mt-1 text-[11px] text-muted-foreground">
                                        Re-runs the line from this phase; any older run is
                                        superseded. Feedback is optional - it is journaled, then
                                        steers the revision verbatim.
                                    </p>
                                    <div className="flex flex-col gap-1.5">
                                        <textarea
                                            ref={redriveRef}
                                            value={redriveNote}
                                            onChange={(e) => setRedriveNote(e.target.value)}
                                            rows={3}
                                            placeholder="What should change? Ask the co-pilot to draft it - its ```redrive block stages here."
                                            className="w-full resize-none rounded-md border border-input bg-background px-2.5 py-2 text-xs leading-relaxed outline-none focus:border-link"
                                        />
                                        <div className="flex gap-2">
                                            <Button
                                                type="button"
                                                variant="outline"
                                                className="h-7 flex-1 text-[11px]"
                                                disabled={actionLoading}
                                                onClick={async () => {
                                                    setBusyAct('redrive');
                                                    try {
                                                        await fireRedrive();
                                                    } finally {
                                                        setBusyAct(null);
                                                    }
                                                }}
                                            >
                                                {busyAct === 'redrive'
                                                    ? 'Working…'
                                                    : redriveNote.trim()
                                                      ? 'Re-drive with this feedback'
                                                      : 'Re-drive'}
                                            </Button>
                                            {chat.length > 0 && (
                                                <Button
                                                    type="button"
                                                    variant="ghost"
                                                    className="h-7 text-[11px]"
                                                    disabled={chatBusy}
                                                    title="One co-pilot turn distilling the conversation into a staged redrive block"
                                                    onClick={() =>
                                                        void sendChat(
                                                            repo,
                                                            here,
                                                            'Distill our conversation into re-drive feedback for this phase - imperative, concrete, only what we discussed - inside a fenced ```redrive code block.',
                                                        )
                                                    }
                                                >
                                                    Draft from chat
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div className="min-h-0 flex-1 p-3.5">
                                <CoPilotPanel
                                    messages={chat}
                                    busy={chatBusy}
                                    configured={chatConfigured}
                                    model={chatModel}
                                    references={references}
                                    onSend={(m) => void sendChat(repo, here, m)}
                                    onClear={() => clearChat(repo, 'delivery')}
                                    onToggleReference={toggleReference}
                                    // Only while a gate awaits: a reply's ```redrive block becomes a
                                    // staged card whose chip pre-fills the composer above.
                                    onStageRedrive={
                                        current.status === 'awaiting-gate' && pendingGate
                                            ? (fb) => {
                                                  setRedriveNote(fb);
                                                  openRedrive(current?.phase ?? null);
                                              }
                                            : undefined
                                    }
                                />
                            </div>
                        </Card>
                    </div>
                </>
            )}
        </Cockpit>
    );
};
export default DeliveryDetailPage;
