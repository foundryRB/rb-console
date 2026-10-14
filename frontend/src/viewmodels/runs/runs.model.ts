import type { Run, RunGraph, RunNode } from '@/models';

export const isClose = (phase: string | null | undefined): boolean =>
    phase === 'Stopped' || phase === 'Stopping';

export const tone = (phase: string | null | undefined): string =>
    phase === 'Succeeded'
        ? 'text-[hsl(var(--success))]'
        : phase === 'Running' || phase === 'Pending'
          ? 'text-link'
          : phase === 'Failed' || phase === 'Error'
            ? 'text-destructive'
            : phase === 'Suspended' || isClose(phase)
              ? 'text-amber-400'
              : 'text-muted-foreground';

export const dot = (phase: string | null | undefined): string =>
    phase === 'Succeeded'
        ? 'bg-[hsl(var(--success))]'
        : phase === 'Running' || phase === 'Pending'
          ? 'bg-primary animate-pulse'
          : phase === 'Failed' || phase === 'Error'
            ? 'bg-destructive'
            : phase === 'Stopping'
              ? 'bg-amber-400 animate-pulse' // still draining its current step
              : phase === 'Suspended' || phase === 'Stopped'
                ? 'bg-amber-400'
                : 'bg-muted-foreground/40';

export const border = (phase: string | null | undefined, selected: boolean): string =>
    selected
        ? 'border-link ring-1 ring-link/50'
        : phase === 'Succeeded'
          ? 'border-[hsl(var(--success))]/40'
          : phase === 'Failed' || phase === 'Error'
            ? 'border-destructive/50'
            : phase === 'Running' || phase === 'Pending'
              ? 'border-link/50'
              : phase === 'Suspended' || isClose(phase)
                ? 'border-amber-400/50'
                : 'border-border';

export const stopTitle = (r: Run): string | undefined =>
    r.stop === 'superseded'
        ? 'Stopped by the Console when a newer drive of this delivery took over - not a failure'
        : r.stop === 'operator'
          ? 'Stopped by the operator (Stop/Terminate) - not a failure'
          : undefined;

export const fmt = (iso: string | null): string =>
    iso ? iso.replace('T', ' ').replace('Z', '').slice(5, 16) : '-';

export const wasStopped = (n: RunNode): boolean =>
    Boolean(
        n.message &&
        (n.message.includes('Stopped with strategy') || n.message.includes('exit code 143')),
    );

export const shownPhase = (n: RunNode): string =>
    (n.phase === 'Failed' || n.phase === 'Error') && wasStopped(n) ? 'Stopped' : (n.phase ?? '-');

export const shownTone = (n: RunNode): string =>
    (n.phase === 'Failed' || n.phase === 'Error') && wasStopped(n)
        ? 'text-amber-400'
        : tone(n.phase);

export const dur = (a: string | null, b: string | null): string => {
    if (!a) return '-';
    const end = b ? Date.parse(b) : Date.now();
    const s = Math.max(0, Math.round((end - Date.parse(a)) / 1000));
    return s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`;
};

export const ago = (iso: string | null): string => {
    if (!iso) return '';
    const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
    if (s < 90) return 'just now';
    if (s < 5400) return `${Math.round(s / 60)}m ago`;
    if (s < 129600) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
};

/** Why a failed run stopped (#181): the refusal line of its last failed worker step, as the
 *  worker wrote it, else that step's executor message. Null for a run that did not fail, or
 *  one the operator or a newer drive stopped - those carry no refusal. */
export const lastRefusal = (graph: RunGraph | null | undefined): string | null => {
    if (!graph || (graph.phase !== 'Failed' && graph.phase !== 'Error') || graph.stop) return null;
    const failed = graph.nodes
        .filter((n) => n.type === 'Pod' && (n.phase === 'Failed' || n.phase === 'Error'))
        .filter((n) => !wasStopped(n))
        .sort((a, b) => (a.finishedAt ?? '').localeCompare(b.finishedAt ?? ''));
    const last = failed[failed.length - 1];
    if (!last) return null;
    return last.refusal?.trim() || last.message?.trim() || null;
};
