import { ObservationNotice } from '@/views/atoms/ObservationNotice';
import { useCopilot } from '@/viewmodels/copilot';
import { useEffect, useMemo, useState } from 'react';

import { cn } from '@/utils';
import { EMPTY_CHAT, chatKey } from '@/viewmodels/copilot';
import { useAppearance } from '@/viewmodels/appearance';
import { useMaintenance } from '@/viewmodels/maintenance';
import { selectClosedPr, selectTicketLine, selectLinkedPr } from '@/viewmodels/maintenance';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { CoPilotPanel } from '@/views/organisms/CoPilotPanel';

import { ComplexityMeter } from '@/views/atoms/ComplexityMeter';
import { PaneToggle } from '@/views/atoms/PaneToggle';
import { PriorityArrow } from '@/views/atoms/PriorityArrow';
import { RecordDocument } from '@/views/organisms/RecordDocument';
import { TicketLine } from '@/views/atoms/TicketLine';
import { TypeBadge } from '@/views/atoms/TypeBadge';
import { VerdictPill } from '@/views/atoms/VerdictPill';
import { ChecksDot } from '@/views/atoms/ChecksDot';
import { PrDiff } from '@/views/molecules/PrDiff';

import { MaintenanceRunsPanel } from '@/views/organisms/MaintenanceRunsPanel';
import { BacklogSkeleton } from '@/views/atoms/BacklogSkeleton';
import {
    MODES,
    maintRunsFor,
    runInFlight,
    runLabel,
    DRIVE_IN_FLIGHT,
} from '@/viewmodels/maintenance/maintenancePresentation.model';

export const MaintenancePane: React.FC<{
    repo: string;
    initialTicket?: number | null;
    /** Whether this repo has NO open delivery line (the guard: the switch is offered only then).
     *  The cockpit knows it as `current?.status === 'not-a-delivery'`. */
    /** Called with the prepared delivery prompt after a successful switch, so the cockpit can
     *  flip to the Delivery view and pre-fill the establish form. */
    onSwitchToDelivery?: (prompt: string) => void;
}> = ({ repo, initialTicket = null, onSwitchToDelivery }) => {
    const {
        state,
        stateLoading,
        stateError,
        loadState,
        substance,
        loadSubstance,
        clearSubstance,
        drive,
        merge,
        closeTicket,
        switchToDelivery,
        actBusy,
        actError,
        driveNote,
        clearAct,
        runs,
        loadRuns,
    } = useMaintenance();
    const { chatConfigured, chatModel, sendChat, clearChat } = useCopilot();
    // This pane's own thread: (repo, maintenance). It never shows a delivery thread, or
    // another repo's - each is a distinct key in the store.
    const chat = useCopilot((s) => s.chats[chatKey(repo, 'maintenance')] ?? EMPTY_CHAT);
    const chatBusy = useCopilot((s) => Boolean(s.chatBusyKeys[chatKey(repo, 'maintenance')]));

    const { resolved } = useAppearance();
    const [mode, setMode] = useState('gated');
    // The open ticket (null -> the backlog picker) and the stop shown on its line
    // (null -> the ticket's current stop, derived). Seeded from initialTicket so the Inbox can
    // deep-link straight to a ticket's cockpit; null when opened from the picker as before.
    const [ticketN, setTicketN] = useState<number | null>(initialTicket);
    const [stopSel, setStopSel] = useState<string | null>(null);
    // Below lg the cockpit and the acts rail can't sit side by side; a tab picks which shows.
    const [pane, setPane] = useState<'work' | 'acts'>('work');

    useEffect(() => {
        void loadState(repo);
        void loadRuns();
        const t = setInterval(() => {
            void loadState(repo);
            void loadRuns();
        }, 15000);
        return () => clearInterval(t);
    }, [repo, loadState, loadRuns]);

    // Reset the open ticket + stop when the repo changes - during render (the repo's
    // "adjust state on a prop change" pattern), not in an effect.
    const [viewedRepo, setViewedRepo] = useState(repo);
    if (repo !== viewedRepo) {
        setViewedRepo(repo);
        // Honor a deep-link into the new repo (the Inbox may point at another repo's ticket);
        // otherwise land on its backlog, as a plain repo switch always did.
        setTicketN(initialTicket);
        setStopSel(null);
        clearSubstance();
    }

    const stateForRepo = state?.repo === repo ? state : null;

    const pos = stateForRepo?.positions;
    const issues = pos?.issues ?? [];
    const driven = stateForRepo?.driven ?? [];

    const myRuns = useMemo(() => maintRunsFor(runs, repo), [runs, repo]);
    const inFlightRun = myRuns.find((r) => runInFlight(r.phase)) ?? null;

    // The open ticket and its derived line.
    const ticket = ticketN != null ? (issues.find((i) => i.number === ticketN) ?? null) : null;
    const cells = useMemo(
        () => (ticket ? selectTicketLine(stateForRepo, ticket.number) : []),
        [ticket, stateForRepo],
    );
    // The ticket's PR, merged-aware like the strip: the OPEN review record if any, else the
    // one that already left the open list (merged or closed). Without this the pane read only
    // open PRs, so a merged ticket showed "No PR" everywhere and "Re-drive" - disagreeing with
    // the strip's "merged / close #n".
    const ticketControls = ticket ? stateForRepo?.ticket_controls?.[String(ticket.number)] : null;
    const canSwitchToDelivery = ticketControls?.can_switch_to_delivery ?? false;
    const openPr = ticket ? selectLinkedPr(stateForRepo, ticket.number) : null;
    const closedPr = ticket && !openPr ? selectClosedPr(stateForRepo, ticket.number) : null;
    const pr = openPr ?? closedPr;
    const prMerged = ticketControls?.pr_merged ?? false;

    // The runs each stop shows, scoped from this repo's maint runs. Resolve: the ticket's resolve
    // runs (gated or one-shot). Review: the PR's standalone review runs (gated) AND the ticket's
    // one-shot resolve runs (whose second step reviews that PR), so the review is watchable at the
    // Review stop whichever ceremony drove it - one-shot's review isn't a separate Workflow, it is
    // a step of the resolve run, and Stop/Terminate there stops the whole one-shot drive (correct:
    // it is one drive).
    const resolveRuns = useMemo(
        () =>
            ticket
                ? myRuns.filter(
                      (r) =>
                          r.maintenance === 'resolve' && String(r.ticket) === String(ticket.number),
                  )
                : [],
        [myRuns, ticket],
    );
    const reviewRuns = useMemo(
        () =>
            ticket && pr
                ? myRuns.filter(
                      (r) =>
                          (r.maintenance === 'review' && String(r.ticket) === String(pr.number)) ||
                          (r.maintenance === 'resolve' &&
                              r.mode === 'one-shot' &&
                              String(r.ticket) === String(ticket.number)),
                  )
                : [],
        [myRuns, ticket, pr],
    );
    // The in-flight run for THIS ticket (its resolve, or a review on its PR). The repo-wide
    // inFlightRun above is only the backlog's "something is active in this repo" hint; the ticket
    // cockpit's own live badge must scope to the open ticket, or it lights up "Running" on a ticket
    // doing nothing while a DIFFERENT ticket's resolve runs - the phantom the operator smelled.
    const ticketInFlight =
        [...resolveRuns, ...reviewRuns].find((r) => runInFlight(r.phase)) ?? null;

    // The engine's one-shot judgement for this ticket, if it drove one - the Merge stop shows it
    // (the engine merges on a recorded PASS, re-drives on a FAIL, or parks the PR for the operator).
    const drivenHere = ticket ? (driven.find((d) => d.ticket === ticket.number) ?? null) : null;

    const currentKey = ticketControls?.default_stop ?? 'ticket';
    const active = stopSel ?? currentKey;
    const activeCell = cells.find((c) => c.key === active) ?? null;

    // A signature of this ticket's resolve/review runs by phase. It changes when any of them
    // transitions (notably to a terminal phase), which is the one substance-affecting event the
    // effect deps below otherwise miss: a review run posting a fresh review + verdict, or a
    // re-drive pushing new commits, both leave pr.number unchanged. Including it re-fetches the
    // PR substance when a run finishes, so the new reviews and diff appear without leaving and
    // re-opening the stop (the pill self-heals off the state poll; the substance did not).
    const stopRunsPhase = [...resolveRuns, ...reviewRuns]
        .map((r) => `${r.run_id ?? r.name}:${r.phase}`)
        .join('|');

    // Load the active stop's substance: the issue body for Ticket; the PR (diff + reviews) for
    // Review. Resolve reads the runs directly, Merge reads the PR position - nothing to fetch.
    useEffect(() => {
        if (!ticket) return;
        if (active === 'ticket') void loadSubstance(repo, 'issue', ticket.number);
        else if (active === 'review' && pr) void loadSubstance(repo, 'pr', pr.number);
    }, [ticket?.number, active, pr?.number, repo, loadSubstance, stopRunsPhase]); // eslint-disable-line react-hooks/exhaustive-deps

    // Drive an act, then land on the stop where its result shows, so a drive never looks like it
    // did nothing: a resolve's worker stages + logs on the Resolve stop; a review's live run and
    // then its fresh verdict on the Review stop (the run, reviews, and verdict pill update there).
    const runAct = async (act: string, target: number | null, m: string) => {
        await drive(repo, act, target, m);
        if (!useMaintenance.getState().actError)
            setStopSel(act === 'review' ? 'review' : 'resolve');
    };

    // Issue #13: a ticket the resolve worker judged too big for a maintenance scope carries the
    // delivery-scale label and a prepared delivery brief: a marked comment, or the ticket body
    // itself when no comment carries the marker. Offer "Switch to Delivery" - alongside the
    // re-drive, never instead of it - gated on the repo having no open delivery line
    // (canSwitchToDelivery). The switch hides the ticket and hands the prepared brief to the
    // cockpit, which flips to the Delivery view and pre-fills the establish form.
    const deliveryScale = ticketControls?.delivery_scale ?? false;
    const wrongRepo = ticketControls?.wrong_repo ?? false;
    const doSwitch = async () => {
        if (!ticket) return;
        const prompt = await switchToDelivery(repo, ticket.number);
        // null is an error (surfaced as actError); "" is a valid switch with no prepared prompt.
        if (prompt != null) onSwitchToDelivery?.(prompt);
    };

    const mergeBlocked = ticketControls?.merge_blocked ?? null;
    const resolveRan = ticketControls?.resolve_ran ?? false;
    const nextAct = ticketControls?.next_act;
    // The resolve / re-drive control: the ceremony-mode picker + the drive button. Rendered as
    // the primary action when the ticket wants a resolve, AND as an always-available secondary
    // "run another resolve" escape hatch while a PR is open - the affordance the pre-cockpit acts
    // rail always had (a resolve was drivable on any ticket). The single-primary line dropped it,
    // so a resolution you dislike could dead-end with only Review/Merge offered; this hands it
    // back. `target` is passed in (never a possibly-null `ticket`) so it is null-safe at the body
    // level. Only one nextAct branch renders at a time, so the mode radiogroup is never duplicated.
    const renderResolveControl = (target: number) => (
        <>
            <div className="flex flex-col gap-1" role="radiogroup" aria-label="Ceremony mode">
                {MODES.filter((m) => !state?.action.modes || state.action.modes.includes(m.id)).map(
                    (m) => (
                        <label
                            key={m.id}
                            className={cn(
                                'flex cursor-pointer items-baseline gap-2 rounded-md border px-2.5 py-1.5 text-xs',
                                mode === m.id
                                    ? 'border-link/60 bg-primary/10'
                                    : 'border-border hover:border-link/40',
                            )}
                            title={m.hint}
                        >
                            <input
                                type="radio"
                                name="maint-mode"
                                checked={mode === m.id}
                                onChange={() => setMode(m.id)}
                                className="accent-[hsl(var(--primary))]"
                            />
                            <span className="font-semibold">{m.label}</span>
                            <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">
                                {m.hint}
                            </span>
                        </label>
                    ),
                )}
            </div>
            <Button
                type="button"
                className="mt-3 h-8 w-full text-xs"
                disabled={actBusy}
                title={`Drive resolve-ticket on #${target} in ${mode} mode`}
                onClick={() => void runAct('resolve', target, mode)}
            >
                {resolveRan ? `Re-drive #${target} · ${mode}` : `Resolve #${target} · ${mode}`}
            </Button>
        </>
    );

    return (
        <>
            <PaneToggle
                options={[
                    { key: 'work', label: 'Loop' },
                    { key: 'acts', label: 'Acts' },
                ]}
                active={pane}
                onSelect={(k) => setPane(k as 'work' | 'acts')}
            />
            <div className="grid min-h-[560px] flex-1 grid-cols-1 gap-3 lg:min-h-[calc(100dvh-320px)] lg:grid-cols-[minmax(0,1fr)_400px]">
                <Card
                    className={cn(
                        'app-glass rb-maintenance min-h-0 min-w-0 flex-col gap-3 p-4',
                        pane === 'work' ? 'flex' : 'hidden lg:flex',
                    )}
                >
                    {!ticket ? (
                        // ---- The PICKER: the open backlog, the fleet-of-tickets. ----
                        <>
                            <div className="flex flex-none flex-wrap items-center gap-2">
                                <h2 className="text-sm font-semibold tracking-tight">
                                    Maintenance
                                </h2>
                                <span className="text-[11px] text-muted-foreground">
                                    Pick a ticket to open its line. Each ticket is one line:
                                    resolve, review, merge.
                                </span>
                                {inFlightRun && (
                                    <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-link/50 bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-link">
                                        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                                        {runLabel(inFlightRun)} · {inFlightRun.phase}
                                    </span>
                                )}
                                {stateLoading && (
                                    <span className="text-[10px] text-muted-foreground">
                                        refreshing…
                                    </span>
                                )}
                            </div>
                            <ObservationNotice
                                error={stateError}
                                freshness={stateForRepo?.freshness}
                                hasData={Boolean(stateForRepo)}
                            />
                            <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto pr-1">
                                {stateForRepo == null ? (
                                    // This repo's state isn't loaded yet: a skeleton, not the empty
                                    // message (which would falsely read "no tickets" mid-fetch) and
                                    // never the previous repo's rows. The error, if any, shows above.
                                    stateError ? null : (
                                        <BacklogSkeleton />
                                    )
                                ) : issues.length === 0 ? (
                                    <p className="py-6 text-center text-xs text-muted-foreground">
                                        No open tickets - an empty backlog is a result, not an
                                        error.
                                    </p>
                                ) : (
                                    issues.map((i) => {
                                        const line = selectTicketLine(stateForRepo, i.number);
                                        const stalled = line.some(
                                            (c) => c.key === 'review' && c.step === 'stalled',
                                        );
                                        const at =
                                            line.find(
                                                (c) => c.step === 'failed' || c.step === 'current',
                                            ) ??
                                            [...line].reverse().find((c) => c.step !== 'pending');
                                        // A resolve run in flight for THIS ticket right now (the heavy act the
                                        // operator leaves running and must not re-drive). The backlog's
                                        // "being tackled" flag, the same signal the Fleet Inbox surfaces; a
                                        // live review shows on the ticket's own header when opened, and the
                                        // merge-ready state stays legible for a PASS whose PR is being re-reviewed.
                                        const running = myRuns.some(
                                            (r) =>
                                                (r.phase === 'Running' || r.phase === 'Pending') &&
                                                r.maintenance === 'resolve' &&
                                                String(r.ticket) === String(i.number),
                                        );
                                        return (
                                            <button
                                                key={i.number}
                                                type="button"
                                                onClick={() => {
                                                    setTicketN(i.number);
                                                    setStopSel(null);
                                                }}
                                                className="flex flex-wrap items-baseline gap-2 rounded-lg border border-border bg-well/20 px-3.5 py-2.5 text-left text-xs hover:border-link/40"
                                            >
                                                {/* The signals rail: priority arrow + complexity meter, a fixed-width
                                                leading column so they align across rows (empty when a ticket carries
                                                no marker - the clean-repo case). */}
                                                <span className="flex w-11 flex-none items-center gap-1.5 self-center">
                                                    <PriorityArrow value={i.priority} />
                                                    <ComplexityMeter value={i.complexity} />
                                                </span>
                                                <span className="font-mono text-[11px] font-semibold text-link">
                                                    #{i.number}
                                                </span>
                                                <TypeBadge value={i.type} />
                                                <span className="font-medium text-foreground">
                                                    {i.title}
                                                </span>
                                                {i.labels.map((lb) => (
                                                    <span
                                                        key={lb}
                                                        className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground"
                                                    >
                                                        {lb}
                                                    </span>
                                                ))}
                                                {running ? (
                                                    <span
                                                        className="inline-flex items-center gap-1 rounded-full border border-link/50 bg-primary/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wide text-link"
                                                        title="A maintenance run is in flight for this ticket right now - watch it, don't re-drive."
                                                    >
                                                        <span className="h-1 w-1 rounded-full bg-primary animate-pulse" />
                                                        running
                                                    </span>
                                                ) : stalled ? (
                                                    <span
                                                        className="rounded-full border border-destructive/50 bg-destructive/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wide text-destructive"
                                                        title="A resolve run went green but no PR is visible - verify it merged, or re-drive."
                                                    >
                                                        stalled
                                                    </span>
                                                ) : at && at.key !== 'ticket' ? (
                                                    <span className="rounded-full border border-border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-muted-foreground">
                                                        at {at.label.toLowerCase()}
                                                    </span>
                                                ) : null}
                                                <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                                                    {i.author}
                                                </span>
                                            </button>
                                        );
                                    })
                                )}
                            </div>
                        </>
                    ) : (
                        // ---- The TICKET COCKPIT: the line (State) + the selected stop (Substance). ----
                        <>
                            <div className="flex flex-none flex-wrap items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setTicketN(null);
                                        setStopSel(null);
                                    }}
                                    className="rounded-md border border-border px-2 py-1 font-mono text-[11px] text-muted-foreground hover:border-link/50 hover:text-link"
                                >
                                    ← backlog
                                </button>
                                <PriorityArrow value={ticket.priority} className="text-base" />
                                <ComplexityMeter value={ticket.complexity} />
                                <TypeBadge value={ticket.type} />
                                <b className="min-w-0 flex-1 truncate text-sm">
                                    #{ticket.number} {ticket.title}
                                </b>
                                {ticketInFlight && (
                                    <span className="inline-flex items-center gap-1.5 rounded-full border border-link/50 bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-link">
                                        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                                        {ticketInFlight.phase}
                                    </span>
                                )}
                                <a
                                    href={ticket.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="font-mono text-[10px] text-muted-foreground hover:text-link"
                                >
                                    GitHub ↗
                                </a>
                            </div>

                            {/* STATE: the ticket's line, the spine - click a stop to inspect it. */}
                            <div className="flex-none rounded-lg border border-border bg-well/10 px-4 pb-3 pt-4">
                                <TicketLine cells={cells} selected={active} onSelect={setStopSel} />
                            </div>

                            {/* SUBSTANCE: the selected stop, rendered natively. */}
                            <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto pr-1">
                                {activeCell && (
                                    <p className="flex-none text-[11px] text-muted-foreground">
                                        {activeCell.hint}
                                    </p>
                                )}

                                {active === 'ticket' &&
                                    (substance?.kind === 'issue' &&
                                    substance.number === ticket.number ? (
                                        <div className="rounded-lg border border-border bg-well/10 p-4">
                                            <RecordDocument
                                                text={substance.body || '(no description)'}
                                            />
                                        </div>
                                    ) : (
                                        <p className="text-xs text-muted-foreground">
                                            Loading the issue…
                                        </p>
                                    ))}

                                {active === 'resolve' && (
                                    <MaintenanceRunsPanel
                                        key={`resolve-${ticket.number}`}
                                        repo={repo}
                                        freshAct="resolve"
                                        runs={resolveRuns}
                                        freshTarget={ticket.number}
                                        emptyHint="No resolve run yet. Drive Resolve and its worker appears here, with its stages and live logs."
                                    />
                                )}

                                {/* The Review stop: the PR and its fresh-eyes verdict, one stop. It leads with
                                    the live review run - status, node band, controls, logs - so a driven Review
                                    (a gated review Workflow, or a one-shot resolve's review step) is watchable
                                    and stoppable at once; then the PR itself, its diff and any posted reviews. */}
                                {active === 'review' &&
                                    (!pr ? (
                                        <p className="py-6 text-center text-xs text-muted-foreground">
                                            No PR yet. Resolve the ticket and its PR opens here for
                                            its fresh-eyes review.
                                        </p>
                                    ) : (
                                        <div className="flex flex-col gap-3">
                                            <MaintenanceRunsPanel
                                                key={`review-${pr.number}`}
                                                repo={repo}
                                                freshAct="review"
                                                runs={reviewRuns}
                                                freshTarget={pr.number}
                                                emptyHint="No review run in flight. Drive Review and its fresh-eyes worker appears here - live status, stages, logs, and Stop / Terminate. (A one-shot drive reviews inside its resolve run, and shows here too.)"
                                            />
                                            {substance?.kind === 'pr' &&
                                            substance.number === pr.number ? (
                                                <div className="flex flex-col gap-3">
                                                    <div className="flex flex-wrap items-center gap-2 text-xs">
                                                        <b className="text-sm">
                                                            #{substance.number} {substance.title}
                                                        </b>
                                                        {closedPr ? (
                                                            <span
                                                                className={cn(
                                                                    'rounded px-1.5 py-0.5 font-mono text-[9px] uppercase',
                                                                    prMerged
                                                                        ? 'bg-[hsl(var(--success))]/15 text-[hsl(var(--success))]'
                                                                        : 'bg-muted text-muted-foreground',
                                                                )}
                                                            >
                                                                {prMerged ? 'merged' : 'closed'}
                                                            </span>
                                                        ) : (
                                                            <>
                                                                <ChecksDot checks={pr.checks} />
                                                                <VerdictPill verdict={pr.verdict} />
                                                            </>
                                                        )}
                                                        <a
                                                            href={substance.url}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            className="ml-auto font-mono text-[10px] text-muted-foreground hover:text-link"
                                                        >
                                                            GitHub ↗
                                                        </a>
                                                    </div>
                                                    {substance.files &&
                                                    substance.files.length > 0 ? (
                                                        <PrDiff
                                                            files={substance.files}
                                                            dark={resolved === 'dark'}
                                                        />
                                                    ) : (
                                                        <p className="text-[11px] text-muted-foreground">
                                                            The diff could not be read - the GitHub
                                                            link above is the fallback.
                                                        </p>
                                                    )}
                                                    {(substance.reviews ?? []).length > 0 ? (
                                                        <div className="flex flex-col gap-1.5">
                                                            {(substance.reviews ?? []).map(
                                                                (r, i) => (
                                                                    <details
                                                                        key={i}
                                                                        open
                                                                        className="rounded-lg border border-border bg-well/20"
                                                                    >
                                                                        <summary className="cursor-pointer px-3 py-2 font-mono text-[11px] text-muted-foreground">
                                                                            {r.author} ·{' '}
                                                                            {r.submitted_at}
                                                                        </summary>
                                                                        <div className="border-t border-border p-3">
                                                                            <RecordDocument
                                                                                text={r.body}
                                                                            />
                                                                        </div>
                                                                    </details>
                                                                ),
                                                            )}
                                                        </div>
                                                    ) : (
                                                        <p className="text-xs text-muted-foreground">
                                                            No fresh-eyes verdict posted yet.
                                                        </p>
                                                    )}
                                                </div>
                                            ) : (
                                                <p className="text-xs text-muted-foreground">
                                                    Loading the PR…
                                                </p>
                                            )}
                                        </div>
                                    ))}

                                {active === 'merge' && (
                                    <div className="flex flex-col gap-2">
                                        {/* The engine's one-shot judgement, when it drove this ticket: the merge is
                                            its deterministic act over the recorded verdict, never a worker's. Shows
                                            here so a one-shot's auto-merge / re-drive / park is visible at the Merge
                                            stop, not only as a one-liner in the Act rail. */}
                                        {drivenHere && (
                                            <div className="rounded-lg border border-link/40 bg-primary/5 px-3 py-2 text-xs">
                                                <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-link">
                                                    one-shot engine
                                                </div>
                                                <p className="mt-1 text-[11px] text-muted-foreground">
                                                    {drivenHere.result ||
                                                        'Watching this drive - it merges on a recorded VERDICT: PASS with green checks, re-drives the resolve on a FAIL (bounded), else parks the PR here for you. No agent ever merges.'}
                                                </p>
                                            </div>
                                        )}
                                        {!pr ? (
                                            <p className="py-6 text-center text-xs text-muted-foreground">
                                                No PR to merge yet.
                                            </p>
                                        ) : prMerged ? (
                                            <div className="flex flex-col gap-2 rounded-lg border border-border bg-well/10 p-4 text-xs">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <b className="text-sm">
                                                        PR #{pr.number} merged
                                                    </b>
                                                    <span className="rounded bg-[hsl(var(--success))]/15 px-1.5 py-0.5 font-mono text-[9px] uppercase text-[hsl(var(--success))]">
                                                        merged
                                                    </span>
                                                </div>
                                                <p className="text-[11px] text-muted-foreground">
                                                    The PR shipped, but the merge did not auto-close
                                                    #{ticket.number} (the closing keyword was
                                                    missing from its body). Close the ticket to
                                                    finish the loop.
                                                </p>
                                            </div>
                                        ) : closedPr ? (
                                            <div className="flex flex-col gap-2 rounded-lg border border-border bg-well/10 p-4 text-xs">
                                                <b className="text-sm">
                                                    PR #{pr.number} closed unmerged
                                                </b>
                                                <p className="text-[11px] text-muted-foreground">
                                                    The PR was closed without merging - the resolve
                                                    did not land. Re-drive #{ticket.number}.
                                                </p>
                                            </div>
                                        ) : (
                                            <div className="flex flex-col gap-2 rounded-lg border border-border bg-well/10 p-4 text-xs">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <b className="text-sm">Merge #{pr.number}</b>
                                                    <ChecksDot checks={pr.checks} />
                                                    <VerdictPill verdict={pr.verdict} />
                                                    {pr.contributor && (
                                                        <span
                                                            className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] uppercase text-muted-foreground"
                                                            title="Authored by someone other than one of the console's own identities. Informational - it changes nothing about how this PR is reviewed or merged."
                                                        >
                                                            contributor
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-[11px] text-muted-foreground">
                                                    {mergeBlocked
                                                        ? `Blocked: ${mergeBlocked}.`
                                                        : 'A fresh-eyes PASS with green checks. Merging rebases under fc-git; the closing keyword fires and the ticket closes. Merge is the handover to CD.'}
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </Card>

                {/* ---- The acts rail: the ACTION for the current stop + the co-pilot. ---- */}
                <Card
                    className={cn(
                        'min-h-0 flex-col p-0',
                        pane === 'acts' ? 'flex' : 'hidden lg:flex',
                    )}
                >
                    <div className="flex-none border-b border-border px-3.5 py-2.5">
                        <b className="text-sm">Act</b>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                            The act for the stop you're on. Each maps 1:1 to a gh/git command; the
                            workers pull the live skills.
                        </p>
                    </div>

                    <div className="flex-none px-3.5 pt-3">
                        {!ticket ? (
                            <p className="text-xs text-muted-foreground">
                                Pick a ticket to see its line and the act it's ready for.
                            </p>
                        ) : (
                            <>
                                {/* Switch to Delivery (issue #13): a ticket a resolve run judged too big
                                    for a maintenance scope. Offered ABOVE the resolve/re-drive controls,
                                    never instead of them - the operator can switch, or re-drive below to
                                    force a maintenance resolve anyway. Gated on no open delivery line. */}
                                {deliveryScale && canSwitchToDelivery && (
                                    <div className="mb-3 rounded-lg border border-link/40 bg-primary/5 p-3">
                                        <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-link">
                                            delivery-scale
                                        </span>
                                        <p className="mt-1 text-[11px] text-muted-foreground">
                                            A resolve run judged #{ticket.number} too big for a
                                            maintenance scope and prepared a delivery line for it.
                                            Switch to open that line with its request pre-filled
                                            from the brief on the ticket, or re-drive below to force
                                            a maintenance resolve anyway.
                                        </p>
                                        <Button
                                            type="button"
                                            className="mt-2 h-8 w-full text-xs"
                                            disabled={actBusy}
                                            title="Hide this ticket from the loop and open the Delivery view with the prepared request pre-filled"
                                            onClick={() => void doSwitch()}
                                        >
                                            Switch #{ticket.number} to Delivery →
                                        </Button>
                                    </div>
                                )}
                                {/* Wrong repo (issue #35): the fix lives elsewhere, so this loop
                                    cannot produce a PR for it however many times it is driven.
                                    Named above the resolve controls, which stay available - the
                                    agent's locus judgement is a judgement, not a fact. */}
                                {wrongRepo && (
                                    <div className="mb-3 rounded-lg border border-destructive/40 bg-destructive/5 p-3">
                                        <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-destructive">
                                            wrong repo
                                        </span>
                                        <p className="mt-1 text-[11px] text-muted-foreground">
                                            A resolve run found #{ticket.number}'s fix lives in
                                            another repo - the ticket names which one. Nothing here
                                            can branch, test, or open a PR for code this repo does
                                            not hold, so the run parked instead of retrying.
                                            Transfer the ticket to the repo that owns the code and
                                            drive it there; re-drive below only if you think the
                                            locus call was wrong.
                                        </p>
                                    </div>
                                )}
                                {deliveryScale && !canSwitchToDelivery && (
                                    <div className="mb-3 rounded-md border border-border bg-well/20 px-2.5 py-1.5 text-[11px] text-muted-foreground">
                                        #{ticket.number} is delivery-scale, but this repo already
                                        has an open delivery line - the switch is offered only when
                                        none is open. Manage the existing line, or re-drive to
                                        resolve in maintenance scope.
                                    </div>
                                )}

                                {/* Resolve / re-drive: no PR yet, a stalled run, or a FAIL to address. */}
                                {nextAct === 'resolve' && (
                                    <>
                                        {renderResolveControl(ticket.number)}
                                        {/* A FAIL verdict is a stale artifact: re-driving the resolve fixes the code
                                            but never clears it - only a fresh review posts a new verdict. Offer that
                                            second act here, or the FAIL dead-ends with no way to a new verdict. */}
                                        {openPr && openPr.verdict === 'fail' && (
                                            <>
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    className="mt-2 h-8 w-full text-xs"
                                                    disabled={actBusy}
                                                    title={`Drive review-pr on #${openPr.number} again: fresh eyes re-read the PR and post a new verdict`}
                                                    onClick={() =>
                                                        void runAct(
                                                            'review',
                                                            openPr.number,
                                                            'gated',
                                                        )
                                                    }
                                                >
                                                    Review #{openPr.number} again
                                                </Button>
                                                <p className="mt-1.5 text-[10px] text-muted-foreground">
                                                    Verdict is FAIL. Re-drive to address the
                                                    findings (they thread into the worker as the
                                                    work order), then Review again for a fresh
                                                    verdict.
                                                </p>
                                            </>
                                        )}
                                    </>
                                )}

                                {/* Review: a PR awaiting a fresh-eyes verdict. */}
                                {nextAct === 'review' && pr && (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-8 w-full text-xs"
                                        disabled={actBusy}
                                        title={`Drive review-pr on #${pr.number}: fresh eyes post findings + the verdict`}
                                        onClick={() => void runAct('review', pr.number, 'gated')}
                                    >
                                        Review #{pr.number}
                                    </Button>
                                )}

                                {/* Merge: a PASS - the handover to CD (disabled with the reason if checks block it).
                                    For a Managed app the merge is the home's to perform: the reason stands
                                    where the button would, rather than a button that refuses on press. */}
                                {nextAct === 'merge' && pr && state?.home && (
                                    <p
                                        data-testid="merge-theirs"
                                        className="rounded-md border border-border bg-well/20 px-3 py-2 text-xs text-muted-foreground"
                                    >
                                        #{pr.number} is on{' '}
                                        <span className="font-mono">{state.home.repo}</span>, which
                                        the foundry does not own: the merge is theirs. The ticket
                                        closes when they land it.
                                    </p>
                                )}
                                {nextAct === 'merge' && pr && !state?.home && (
                                    <Button
                                        type="button"
                                        className="h-8 w-full text-xs"
                                        disabled={actBusy || Boolean(mergeBlocked)}
                                        title={
                                            mergeBlocked ??
                                            'gh pr merge --rebase under fc-git: the commits land individually; the closing keyword fires'
                                        }
                                        onClick={() => void merge(repo, pr.number)}
                                    >
                                        {pr.contributor
                                            ? `Merge #${pr.number} (contributor · rebase)`
                                            : `Merge #${pr.number} (rebase)`}
                                    </Button>
                                )}

                                {/* Close: the PR merged but did not auto-close its ticket (the
                                    closing keyword was missing from its body). gh issue close, so
                                    the loop finishes instead of a meaningless Re-drive. */}
                                {nextAct === 'close' && closedPr && (
                                    <Button
                                        type="button"
                                        className="h-8 w-full text-xs"
                                        disabled={actBusy}
                                        title={`PR #${closedPr.number} merged but did not auto-close #${ticket.number}; close it (gh issue close)`}
                                        onClick={() => void closeTicket(repo, ticket.number)}
                                    >
                                        Close #{ticket.number} · PR #{closedPr.number} merged
                                    </Button>
                                )}

                                {/* The escape hatch: run ANOTHER resolve on an open PR whose resolution you
                                    don't want, without waiting for a FAIL verdict to route you here. The
                                    pre-cockpit acts rail always allowed a resolve; the single-primary line only
                                    offers it in the resolve/FAIL states, so a PASS you dislike - or a verdict
                                    stuck 'awaiting' - had no way back to the worker. Offered on an open PR
                                    (review/merge), never once it has merged (re-driving landed work was a real
                                    bug - Close is the only move then). */}
                                {(nextAct === 'review' || nextAct === 'merge') && (
                                    <div className="mt-3 border-t border-border pt-3">
                                        <p className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                                            Not what you wanted? Run another resolve
                                        </p>
                                        {renderResolveControl(ticket.number)}
                                    </div>
                                )}

                                {driveNote && (
                                    <div className="mt-2 flex items-start gap-2 rounded-md border border-border bg-well/20 px-2.5 py-1.5 text-[11px]">
                                        <span className="min-w-0 flex-1">{driveNote}</span>
                                        <button
                                            type="button"
                                            onClick={clearAct}
                                            className="font-mono text-muted-foreground hover:text-foreground"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                )}
                                {actError && (
                                    <div className="mt-2 flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-2.5 py-1.5 text-[11px] text-destructive">
                                        <span className="min-w-0 flex-1">{actError}</span>
                                        <button
                                            type="button"
                                            onClick={clearAct}
                                            className="font-mono hover:text-foreground"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                )}

                                {driven.length > 0 && (
                                    <div className="mt-3 flex flex-col gap-1">
                                        <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                                            one-shot drives · the engine's judge
                                        </span>
                                        {/* Capped and scrolling: the co-pilot below owns the rest of
                                            the rail, and a burst of concurrent drives must not squeeze
                                            it out of the column. */}
                                        <div className="flex max-h-40 flex-col gap-1 overflow-y-auto pr-1">
                                            {driven.map((d) => (
                                                <div
                                                    key={d.handle}
                                                    className="rounded-md border border-border bg-well/20 px-2.5 py-1.5 text-[11px]"
                                                >
                                                    <span className="font-mono text-link">
                                                        #{d.ticket}
                                                    </span>{' '}
                                                    <span className="text-muted-foreground">
                                                        {d.result || DRIVE_IN_FLIGHT}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </div>

                    <div className="mt-3 min-h-0 flex-1 border-t border-border p-3.5">
                        <CoPilotPanel
                            messages={chat}
                            busy={chatBusy}
                            configured={chatConfigured}
                            model={chatModel}
                            references={[]}
                            onSend={(m) => void sendChat(repo, 'maintenance', m)}
                            onClear={() => clearChat(repo, 'maintenance')}
                            onToggleReference={() => undefined}
                            notConfiguredHint={
                                <>
                                    Pick a provider for this project (the masthead form) and the
                                    maintenance co-pilot answers here.
                                </>
                            }
                            emptyHint="Ask about the loop - what needs attention, what a verdict means, which mode fits."
                        />
                    </div>
                </Card>
            </div>
        </>
    );
};
