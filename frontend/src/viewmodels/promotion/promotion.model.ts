import { type PromotionTargetView } from '@/viewmodels/promotion';

export const TONE: Record<PromotionTargetView['state'], string> = {
    unproven: 'border-destructive/50 bg-destructive/5',
    'in-flight': 'border-amber-500/50 bg-amber-500/5',
    pending: 'border-link/60 bg-primary/10',
    current: 'border-[hsl(var(--success))]/40 bg-[hsl(var(--success))]/5',
    unreadable: 'border-border bg-well/20',
};

export const DOT: Record<PromotionTargetView['state'], string> = {
    unproven: 'bg-destructive',
    'in-flight': 'bg-amber-400',
    pending: 'bg-primary animate-pulse',
    current: 'bg-[hsl(var(--success))]',
    unreadable: 'bg-muted-foreground/40',
};

export const LABEL: Record<PromotionTargetView['state'], string> = {
    unproven: 'unproven',
    'in-flight': 'in flight',
    pending: 'pending',
    current: 'up to date',
    unreadable: 'unreadable',
};

export function nextAct(target: PromotionTargetView, repo: string): string {
    // A shut door asks for a different act than every other unreadable row - register the
    // credential, not look at the target - so it is answered before the state is consulted.
    if (target.door_shut) {
        return target.credential
            ? `register ${target.credential} in Settings → Pair credentials`
            : 'name a credential for this pair in the contract';
    }
    if (target.state === 'pending') return `promote ${repo} ${target.name}`;
    if (target.state === 'in-flight') return `${target.door_ref} awaits their review`;
    if (target.state === 'unproven')
        return 'the target serves it; its declared signal does not answer';
    if (target.state === 'unreadable') return 'the target could not be read';
    return 'nothing to do';
}
