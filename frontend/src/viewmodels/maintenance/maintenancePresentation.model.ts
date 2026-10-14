import type { Run } from '@/models';

export function patchSides(patch: string): { original: string; modified: string } {
    const original: string[] = [];
    const modified: string[] = [];
    for (const line of (patch || '').split('\n')) {
        if (line.startsWith('@@')) {
            original.push(line);
            modified.push(line);
        } else if (line.startsWith('+')) {
            modified.push(line.slice(1));
        } else if (line.startsWith('-')) {
            original.push(line.slice(1));
        } else {
            const text = line.startsWith(' ') ? line.slice(1) : line;
            original.push(text);
            modified.push(text);
        }
    }
    return { original: original.join('\n'), modified: modified.join('\n') };
}

export const MODES: { id: string; label: string; hint: string }[] = [
    {
        id: 'gated',
        label: 'Gated',
        hint: 'ticket → PR → fresh-eyes verdict → your merge (the default)',
    },
    {
        id: 'one-shot',
        label: 'One-shot',
        hint: 'the engine merges on a recorded PASS with green checks - your standing authorization for this drive',
    },
    {
        id: 'direct',
        label: 'Direct',
        hint: 'a conventional commit on the default branch; no PR - for changes smaller than the ceremony',
    },
];

export const maintRunsFor = (runs: Run[], repo: string): Run[] =>
    runs.filter((run) => run.repo === repo && run.kind === 'maintenance');

export const isDone = (p?: string | null): boolean =>
    p === 'Succeeded' || p === 'Failed' || p === 'Error' || p === 'Stopped';

export const runInFlight = (p?: string | null): boolean =>
    p === 'Running' || p === 'Pending' || p === 'Suspended' || p === 'Stopping';

export const runLabel = (r: { maintenance?: string | null; ticket?: string | null }): string => {
    const act = r.maintenance || 'run';
    return r.ticket ? `${act} #${r.ticket}` : act;
};

export const fmtTime = (iso: string | null | undefined): string =>
    iso ? iso.replace('T', ' ').replace('Z', '').slice(5, 16) : '-';

export const nameFromHandle = (h: string | null): string | null =>
    h && h.startsWith('live:') ? (h.split(':', 2)[1]?.split('/').pop() ?? null) : null;

export const DRIVE_IN_FLIGHT =
    'running - the engine reads the verdict from GitHub when it finishes';
