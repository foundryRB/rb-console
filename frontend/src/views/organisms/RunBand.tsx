import { Fragment, useState } from 'react';
import type { Run, RunGraph } from '@/models';
import { cn } from '@/utils';
import { RunGraphPanel } from '@/views/molecules/RunGraphPanel';
import { tone, dot, stopTitle, ago } from '@/viewmodels/runs/runs.model';

export const RunBand: React.FC<{
    /** The newest run's graph, polled live by the page. */
    graph: RunGraph;
    /** This surface's run history, newest first; row 0 is the run `graph` describes. */
    runs?: Run[];
    /** Older runs' graphs, fetched once by handle (the page's bandGraphs cache). */
    graphs?: Record<string, RunGraph>;
    /** Ask the page to fetch an older run's graph when its row unfolds. */
    onUnfold?: (handle: string) => void;
    /** Per-node log tails keyed `${handle}::${nodeId}`; with onNeedNodeLogs, the
     * inspector shows the selected step's logs. */
    nodeLogs?: Record<string, string>;
    onNeedNodeLogs?: (handle: string, nodeId: string) => void;
}> = ({ graph, runs, graphs, onUnfold, nodeLogs, onNeedNodeLogs }) => {
    // The unfolded run's handle; null tracks the newest, so a fresh drive's new run
    // unfolds itself the moment it appears at the top.
    const [unfolded, setUnfolded] = useState<string | null>(null);
    const history = runs ?? [];
    const newest = history[0] ?? null;
    const shownHandle = unfolded ?? newest?.handle ?? null;
    const shownGraph =
        !unfolded || unfolded === newest?.handle ? graph : (graphs?.[unfolded] ?? null);

    const rows = history.length > 1 ? history : [];
    const unfold = (r: Run) => {
        if (r.handle === newest?.handle) {
            setUnfolded(null);
            return;
        }
        setUnfolded(r.handle);
        onUnfold?.(r.handle);
    };

    return (
        <div className="border-t border-border bg-well/20">
            {rows.map((r, i) => {
                const open = r.handle === shownHandle;
                return (
                    <Fragment key={r.handle}>
                        <button
                            type="button"
                            onClick={() => unfold(r)}
                            className={cn(
                                'flex w-full items-center gap-2 px-4 py-1.5 text-left transition-colors hover:bg-well/20',
                                i > 0 && 'border-t border-border/60',
                            )}
                            title={
                                open
                                    ? undefined
                                    : i === 0
                                      ? 'Unfold the current run'
                                      : 'Unfold this superseded run - read-only history; the controls above keep acting on the current run'
                            }
                        >
                            <span className="font-mono text-[10px] text-muted-foreground">
                                {open ? '▾' : '▸'}
                            </span>
                            <span
                                className={cn('h-1.5 w-1.5 flex-none rounded-full', dot(r.phase))}
                            />
                            <span className="font-mono text-[11px] font-semibold">
                                run {r.name.split('-').slice(-1)[0]}
                            </span>
                            {/* Two independent facts, deliberately not merged. The phase is the
                                OUTCOME (how it ended); `· superseded` is the RELATION (this is
                                not the newest run), which is why it stays positional and rides
                                on a Succeeded row just as readily as a Stopped one. */}
                            <span
                                className={cn('font-mono text-[10px]', tone(r.phase))}
                                title={stopTitle(r)}
                            >
                                {r.phase}
                            </span>
                            <span className="font-mono text-[10px] text-muted-foreground">
                                {ago(r.finished ?? r.started ?? r.created)}
                                {i > 0 ? ' · superseded' : ''}
                            </span>
                            {r.agents && r.agents.length > 0 && (
                                <span
                                    className="ml-auto truncate font-mono text-[10px] text-muted-foreground"
                                    title="Who ran this run's steps: the playbook catalog agents"
                                >
                                    {r.agents.join(' → ')}
                                </span>
                            )}
                        </button>
                        {open &&
                            (shownGraph ? (
                                <RunGraphPanel
                                    graph={shownGraph}
                                    handle={shownHandle}
                                    nodeLogs={nodeLogs}
                                    onNeedNodeLogs={onNeedNodeLogs}
                                />
                            ) : (
                                <p className="px-4 py-3 text-xs text-muted-foreground">
                                    Loading run…
                                </p>
                            ))}
                    </Fragment>
                );
            })}
            {rows.length === 0 && (
                <RunGraphPanel
                    graph={graph}
                    handle={shownHandle}
                    nodeLogs={nodeLogs}
                    onNeedNodeLogs={onNeedNodeLogs}
                />
            )}
        </div>
    );
};
