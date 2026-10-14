import type { Gate } from '@/models';
import { cn } from '@/utils';

export interface GateListProps {
    gates: Gate[];
    /** The gate awaiting a signature, flagged as pending. */
    pendingGate?: string | null;
}

/** The four delivery gates, each signed (with its date) or flagged pending. */
export const GateList: React.FC<GateListProps> = ({ gates, pendingGate }) => {
    if (gates.length === 0) {
        return <p className="text-xs text-muted-foreground">No gates reached yet.</p>;
    }
    return (
        <ul className="flex flex-col gap-1.5">
            {gates.map((gate) => {
                const pending = gate.signed_on === null;
                const flagged = pending && gate.name === pendingGate;
                return (
                    <li
                        key={gate.name}
                        className={cn(
                            'flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs',
                            flagged
                                ? 'border-link/60 bg-primary/10'
                                : 'border-border bg-secondary/40',
                        )}
                    >
                        <span className="flex items-center gap-2">
                            <span
                                className={cn(
                                    'h-2 w-2 rounded-full',
                                    pending ? 'bg-primary' : 'bg-success',
                                )}
                                aria-hidden="true"
                            />
                            <span className="font-medium capitalize">{gate.name}</span>
                        </span>
                        {pending ? (
                            <span className={cn(flagged ? 'text-link' : 'text-muted-foreground')}>
                                {flagged ? 'awaiting signature' : 'pending'}
                            </span>
                        ) : (
                            <span className="font-mono text-muted-foreground">
                                signed {gate.signed_on}
                            </span>
                        )}
                    </li>
                );
            })}
        </ul>
    );
};
