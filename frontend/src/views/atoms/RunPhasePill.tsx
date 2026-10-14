import { cn } from '@/utils';

export const RunPhasePill: React.FC<{ phase?: string | null; stopped?: boolean }> = ({
    phase,
    stopped,
}) => (
    <span
        className={cn(
            'rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold',
            stopped || phase === 'Stopped' || phase === 'Stopping'
                ? 'border-amber-400/50 text-amber-400'
                : phase === 'Succeeded'
                  ? 'border-[hsl(var(--success))]/40 text-[hsl(var(--success))]'
                  : phase === 'Failed' || phase === 'Error'
                    ? 'border-destructive/50 text-destructive'
                    : phase === 'Suspended'
                      ? 'border-amber-400/50 text-amber-400'
                      : phase === 'Running' || phase === 'Pending'
                        ? 'border-link/50 text-link'
                        : 'border-border text-muted-foreground',
        )}
    >
        {stopped ? 'stopped' : (phase ?? '-')}
    </span>
);
