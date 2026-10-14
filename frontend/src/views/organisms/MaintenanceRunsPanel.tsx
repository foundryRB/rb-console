import { useEffect, useRef, useState } from 'react';
import type { Run } from '@/models';
import { cn } from '@/utils';

import { useMaintenance } from '@/viewmodels/maintenance';

import { RunBand } from '@/views/organisms/RunBand';

import { RunPhasePill } from '@/views/atoms/RunPhasePill';

import {
    isDone,
    runLabel,
    fmtTime,
    nameFromHandle,
} from '@/viewmodels/maintenance/maintenancePresentation.model';

export const MaintenanceRunsPanel: React.FC<{
    repo: string;
    freshAct: string;
    runs: Run[];
    freshTarget?: number | null;
    emptyHint?: string;
}> = ({ repo, freshAct, runs: myRuns, freshTarget, emptyHint }) => {
    const {
        runGraph,
        loadRunGraph,
        runLogs,
        runLogsLoading,
        loadRunLogs,
        stopRun,
        resumeRun,
        actBusy,
        lastRun,
    } = useMaintenance();

    const [sel, setSel] = useState<string | null>(null);
    // The live Argo surface is a toggle: clicking the run row whose surface is open collapses it,
    // so the node band + controls show only for a run the operator deliberately picked - never
    // forced open under the row list. Default is the just-driven / newest run (so a drive is
    // watchable at once); collapsing overrides that until the operator picks a row again.
    const [collapsed, setCollapsed] = useState(false);
    const [showLogs, setShowLogs] = useState(false);
    const [logsFollowing, setLogsFollowing] = useState(true);
    const logsRef = useRef<HTMLPreElement | null>(null);

    // Default to the just-driven run (only when it belongs to THIS stop), else the newest -
    // but honor a manual pick. A fresh handle reads a graph before the list lists it.
    const freshHandle =
        lastRun?.handle &&
        lastRun.handle.startsWith('live:') &&
        lastRun.repo === repo &&
        lastRun.act === freshAct &&
        (freshTarget == null || String(lastRun.target) === String(freshTarget))
            ? lastRun.handle
            : null;
    const selectedHandle = collapsed ? null : (sel ?? freshHandle ?? myRuns[0]?.handle ?? null);
    const selectedRun = myRuns.find((r) => r.handle === selectedHandle) ?? null;
    const selName = selectedRun?.name ?? nameFromHandle(selectedHandle);
    const graphMatches = Boolean(runGraph?.name && selName && runGraph.name === selName);
    const phase = graphMatches ? runGraph?.phase : (selectedRun?.phase ?? null);
    const stopped = Boolean(
        graphMatches && runGraph?.nodes?.some((n) => n.message?.includes('Stopped with strategy')),
    );

    useEffect(() => {
        if (selectedHandle) void loadRunGraph(selectedHandle);
    }, [selectedHandle, loadRunGraph]);

    useEffect(() => {
        if (!selectedHandle || isDone(phase)) return;
        const t = setInterval(() => void loadRunGraph(selectedHandle), 15000);
        return () => clearInterval(t);
    }, [selectedHandle, phase, loadRunGraph]);

    useEffect(() => {
        if (!showLogs || !selectedHandle || !logsFollowing || isDone(phase)) return;
        const t = setInterval(() => void loadRunLogs(selectedHandle), 4000);
        return () => clearInterval(t);
    }, [showLogs, selectedHandle, logsFollowing, phase, loadRunLogs]);
    useEffect(() => {
        const el = logsRef.current;
        if (el && logsFollowing) el.scrollTop = el.scrollHeight;
    }, [runLogs, showLogs, logsFollowing]);

    if (myRuns.length === 0 && !selectedHandle) {
        return (
            <p className="py-6 text-center text-xs text-muted-foreground">
                {emptyHint ??
                    'No runs for this ticket yet. Drive Resolve and its worker appears here, with its stages and live logs.'}
            </p>
        );
    }

    return (
        <div className="flex flex-col gap-3">
            {/* The ticket's runs, newest first: each a selectable row. */}
            <div className="flex flex-col gap-1.5">
                {myRuns.map((r) => (
                    <button
                        key={r.handle}
                        type="button"
                        onClick={() => {
                            // Toggle: clicking the run whose surface is open hides it; clicking any
                            // other row opens that one. So the panel shows only a deliberately-picked run.
                            if (r.handle === selectedHandle) {
                                setCollapsed(true);
                            } else {
                                setSel(r.handle);
                                setCollapsed(false);
                            }
                            setShowLogs(false);
                        }}
                        className={cn(
                            'flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs',
                            r.handle === selectedHandle
                                ? 'border-link/60 bg-primary/10'
                                : 'border-border bg-well/20 hover:border-link/40',
                        )}
                    >
                        <span className="font-mono text-[11px] font-semibold text-foreground">
                            {runLabel(r)}
                        </span>
                        {r.mode && (
                            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] uppercase text-muted-foreground">
                                {r.mode}
                            </span>
                        )}
                        <RunPhasePill phase={r.phase} />
                        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                            {fmtTime(r.created)} · {r.run_id ?? r.name.split('-').slice(-1)[0]}
                        </span>
                    </button>
                ))}
                {myRuns.length === 0 && selectedHandle && (
                    <p className="rounded-lg border border-border bg-well/20 px-3 py-2 text-[11px] text-muted-foreground">
                        {lastRun
                            ? `${lastRun.act}${lastRun.target ? ` #${lastRun.target}` : ''}`
                            : 'run'}{' '}
                        starting - the executor is registering the Workflow…
                    </p>
                )}
            </div>

            {/* The selected run's live Argo surface: controls, the node band, the log tail. */}
            {selectedHandle && (
                <div className="overflow-hidden rounded-lg border border-border">
                    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-well/20 px-3 py-2">
                        <span className="font-mono text-[11px] text-muted-foreground">
                            run{' '}
                            {selectedRun?.run_id ??
                                (nameFromHandle(selectedHandle) ?? '').split('-').slice(-1)[0]}
                        </span>
                        <RunPhasePill phase={phase} stopped={stopped} />
                        {graphMatches && runGraph?.progress && (
                            <span className="font-mono text-[10px] text-muted-foreground">
                                {runGraph.progress}
                            </span>
                        )}
                        <div className="ml-auto flex flex-wrap items-center gap-1.5">
                            {phase === 'Suspended' && (
                                <button
                                    type="button"
                                    onClick={() => void resumeRun(selectedHandle)}
                                    disabled={actBusy}
                                    className="rounded-md border border-border px-2 py-1 text-[11px] hover:border-link/50 disabled:opacity-50"
                                    title="Release a suspended gate"
                                >
                                    Resume
                                </button>
                            )}
                            {!isDone(phase) && (
                                <>
                                    <button
                                        type="button"
                                        onClick={() => void stopRun(selectedHandle, false)}
                                        disabled={actBusy}
                                        className="rounded-md border border-border px-2 py-1 text-[11px] hover:border-destructive/60 hover:text-destructive disabled:opacity-50"
                                        title="Stop lets running steps finish their exit handlers"
                                    >
                                        Stop
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => void stopRun(selectedHandle, true)}
                                        disabled={actBusy}
                                        className="rounded-md border border-border px-2 py-1 text-[11px] hover:border-destructive/60 hover:text-destructive disabled:opacity-50"
                                        title="Terminate kills the run immediately"
                                    >
                                        Terminate
                                    </button>
                                </>
                            )}
                            <button
                                type="button"
                                onClick={() => {
                                    const n = !showLogs;
                                    setShowLogs(n);
                                    if (n) {
                                        setLogsFollowing(true);
                                        void loadRunLogs(selectedHandle);
                                    }
                                }}
                                className="rounded-md border border-border px-2 py-1 text-[11px] hover:border-link/50"
                            >
                                {showLogs ? 'Hide logs' : 'Logs'}
                            </button>
                        </div>
                    </div>

                    {graphMatches && runGraph ? (
                        <RunBand graph={runGraph} />
                    ) : (
                        <p className="px-4 py-3 text-xs text-muted-foreground">
                            Loading run graph…
                        </p>
                    )}

                    {showLogs && (
                        <div className="border-t border-border">
                            <div className="flex items-center justify-between bg-well/30 px-3 py-1">
                                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                                    run logs
                                </span>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setLogsFollowing(true);
                                        void loadRunLogs(selectedHandle);
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
                                className="max-h-72 overflow-auto bg-well/40 p-3 text-[11px] leading-snug text-muted-foreground"
                            >
                                {runLogs == null && runLogsLoading
                                    ? 'Loading logs…'
                                    : runLogs || 'No logs yet.'}
                            </pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
