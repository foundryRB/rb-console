import type { PhaseView } from '@/models';

export type Tone = NonNullable<PhaseView['tone']>;

export const NODE: Record<Tone, string> = {
    done: 'border-[hsl(var(--success))]/40 bg-[hsl(var(--success))]/5',
    running: 'border-link/60 bg-primary/10',
    failed: 'border-destructive/50 bg-destructive/5',
    warn: 'border-amber-500/50 bg-amber-500/5',
    current: 'border-link/50 bg-primary/5',
    locked: 'border-border bg-well/20',
};

export const DOT: Record<Tone, string> = {
    done: 'bg-[hsl(var(--success))]',
    running: 'bg-primary animate-pulse',
    failed: 'bg-destructive',
    warn: 'bg-amber-400',
    current: 'bg-primary',
    locked: 'bg-muted-foreground/40',
};

export const SUB: Record<Tone, string> = {
    done: 'text-[hsl(var(--success))]',
    running: 'text-link',
    failed: 'text-destructive',
    warn: 'text-amber-400',
    current: 'text-link',
    locked: 'text-muted-foreground',
};
