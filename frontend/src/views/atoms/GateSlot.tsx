import type { PhaseView } from '@/models';
import { cn } from '@/utils';

export const GateSlot: React.FC<{ p: PhaseView }> = ({ p }) => {
    const signed = Boolean(p.gate_signed_on);
    const awaiting = !signed && p.record_present;
    const rail = signed ? 'bg-[hsl(var(--success))]/60' : 'bg-border';
    return (
        <div
            className="flex w-16 flex-none flex-col items-center justify-center gap-1 self-stretch"
            title={
                p.gate
                    ? `${p.gate} gate${signed ? ` · signed ${p.gate_signed_on}` : awaiting ? ' · awaiting signature' : ''}`
                    : undefined
            }
        >
            {/* connector · diamond · connector as one flex row - nothing absolute, nothing to
                cross through or drift out of alignment */}
            <div className="flex w-full items-center">
                <span className={cn('h-0.5 min-w-1 flex-1', rail)} />
                <span
                    className={cn(
                        'mx-1 h-[17px] w-[17px] flex-none rotate-45 rounded-[3px] border-2 bg-card',
                        signed
                            ? 'border-[hsl(var(--success))] bg-[hsl(var(--success))]/10'
                            : awaiting
                              ? 'animate-pulse border-link bg-primary/15'
                              : 'border-border',
                    )}
                />
                <span className={cn('h-0.5 min-w-1 flex-1', rail)} />
            </div>
            <span
                className={cn(
                    'font-mono text-[8.5px] font-semibold uppercase tracking-widest',
                    signed ? 'text-[hsl(var(--success))]' : awaiting ? 'text-link' : 'text-faint',
                )}
            >
                {p.gate}
            </span>
        </div>
    );
};
