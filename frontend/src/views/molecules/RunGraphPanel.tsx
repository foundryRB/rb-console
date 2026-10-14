import { Fragment, useEffect, useMemo, useState } from 'react';
import type { RunGraph, RunNode } from '@/models';
import { cn } from '@/utils';

import {
    dot,
    border,
    fmt,
    wasStopped,
    shownPhase,
    shownTone,
    dur,
} from '@/viewmodels/runs/runs.model';

export const RunGraphPanel: React.FC<{
    graph: RunGraph;
    handle: string | null;
    nodeLogs?: Record<string, string>;
    onNeedNodeLogs?: (handle: string, nodeId: string) => void;
}> = ({ graph, handle, nodeLogs, onNeedNodeLogs }) => {
    const steps = useMemo(
        () =>
            graph.nodes
                .filter((n) => n.type === 'Pod' || n.type === 'Suspend')
                .sort((a, b) => (a.startedAt ?? '').localeCompare(b.startedAt ?? '')),
        [graph],
    );
    const [sel, setSel] = useState<string | null>(null);
    const node: RunNode | null = useMemo(() => {
        const picked = steps.find((n) => n.id === sel);
        if (picked) return picked;
        // Default to the most interesting node: the first failure, else the live one, else the last.
        return (
            steps.find((n) => n.phase === 'Failed' || n.phase === 'Error') ??
            steps.find((n) => n.phase === 'Running' || n.phase === 'Suspended') ??
            steps[steps.length - 1] ??
            null
        );
    }, [steps, sel]);

    // The inspector's log tail: fetch on step selection, and keep tailing while the step
    // executes. A Suspend node has no pod, so it never fetches.
    const wantLogs = Boolean(onNeedNodeLogs && handle && node && node.type === 'Pod');
    const nodeId = node?.id ?? null;
    const nodeLive = node?.phase === 'Running' || node?.phase === 'Pending';
    useEffect(() => {
        if (!wantLogs || !handle || !nodeId) return;
        onNeedNodeLogs?.(handle, nodeId);
        if (!nodeLive) return;
        const t = setInterval(() => onNeedNodeLogs?.(handle, nodeId), 5000);
        return () => clearInterval(t);
    }, [wantLogs, handle, nodeId, nodeLive, onNeedNodeLogs]);
    const tail = wantLogs && handle && nodeId ? nodeLogs?.[`${handle}::${nodeId}`] : undefined;

    if (steps.length === 0) {
        return (
            <p className="px-4 py-3 text-xs text-muted-foreground">
                No executor nodes reported yet.
            </p>
        );
    }

    return (
        <>
            <div className="flex items-center gap-2 overflow-x-auto px-4 pb-2.5 pt-3">
                {steps.map((n, i) => (
                    <Fragment key={n.id}>
                        <button
                            type="button"
                            onClick={() => setSel(n.id)}
                            className={cn(
                                'min-w-[120px] flex-none rounded-md border bg-card px-3 py-2 text-left transition-colors hover:border-link/40',
                                border(n.phase, node?.id === n.id),
                            )}
                        >
                            <span className="flex items-center gap-1.5">
                                <span
                                    className={cn(
                                        'h-1.5 w-1.5 flex-none rounded-full',
                                        dot(n.phase),
                                    )}
                                />
                                <span className="truncate font-mono text-[11px] font-semibold">
                                    {n.type === 'Suspend' ? `${n.name} · gate` : n.name}
                                </span>
                            </span>
                            <span
                                className={cn('mt-0.5 block font-mono text-[10px]', shownTone(n))}
                            >
                                {shownPhase(n)}
                                {n.type === 'Pod' && n.startedAt
                                    ? ` · ${dur(n.startedAt, n.finishedAt)}`
                                    : ''}
                            </span>
                            {n.agent && (
                                <span className="mt-0.5 block truncate font-mono text-[10px] text-muted-foreground">
                                    {n.agent}
                                </span>
                            )}
                        </button>
                        {i < steps.length - 1 && <span className="h-0.5 w-3 flex-none bg-border" />}
                    </Fragment>
                ))}
            </div>

            {node && (
                <div className="grid grid-cols-1 border-t border-dashed border-border md:grid-cols-[280px_1fr]">
                    <dl className="grid grid-cols-[auto_1fr] content-start gap-x-4 gap-y-1 border-border px-4 py-3 text-xs md:border-r">
                        <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                            node
                        </dt>
                        <dd className="truncate font-mono">{node.name}</dd>
                        <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                            state
                        </dt>
                        <dd className={cn('font-mono', shownTone(node))}>{shownPhase(node)}</dd>
                        <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                            started
                        </dt>
                        <dd className="font-mono">{fmt(node.startedAt)}</dd>
                        <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                            ran
                        </dt>
                        <dd className="font-mono">
                            {node.startedAt ? dur(node.startedAt, node.finishedAt) : '-'}
                        </dd>
                        {node.agent && (
                            <>
                                <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                                    agent
                                </dt>
                                <dd
                                    className="truncate font-mono"
                                    title="The playbook catalog agent this step ran as"
                                >
                                    {node.agent}
                                </dd>
                            </>
                        )}
                        {node.template && (
                            <>
                                <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                                    template
                                </dt>
                                <dd className="truncate font-mono">{node.template}</dd>
                            </>
                        )}
                    </dl>
                    <div className="flex min-w-0 flex-col gap-2 px-4 py-3">
                        <p
                            className={cn(
                                'text-xs leading-relaxed',
                                wasStopped(node)
                                    ? 'text-amber-400/90'
                                    : node.phase === 'Failed' || node.phase === 'Error'
                                      ? 'text-destructive/90'
                                      : 'text-foreground',
                            )}
                        >
                            {node.message ||
                                (node.type === 'Suspend'
                                    ? 'A gate suspend - the run holds here until the gate is signed, then Resume releases it.'
                                    : 'No message from the executor for this node.')}
                        </p>
                        {node.artifacts.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                                {node.artifacts.map((a) => (
                                    <span
                                        key={a}
                                        className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground"
                                    >
                                        ⎘ {a}
                                    </span>
                                ))}
                            </div>
                        )}
                        {wantLogs && (
                            <div className="min-w-0">
                                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                                    step logs{nodeLive ? ' · following' : ''}
                                </span>
                                <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-well/40 p-2.5 text-[11px] leading-snug text-muted-foreground">
                                    {tail == null
                                        ? 'Loading logs…'
                                        : tail ||
                                          'No logs for this step - none written, or reclaimed before capture.'}
                                </pre>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </>
    );
};
