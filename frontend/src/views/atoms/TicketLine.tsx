import type { TicketCell, TicketStep } from '@/viewmodels/maintenance';
import { cn } from '@/utils';

export interface TicketLineProps {
    cells: TicketCell[];
    /** The stop currently shown in the cockpit; its cell is ringed. */
    selected?: string | null;
    /** When set, each stop is a button that selects it (drives which substance + action show). */
    onSelect?: (key: string) => void;
    className?: string;
}

// The dot per step. Beyond delivery's PhaseStrip: 'failed' (red, filled) and 'stalled' -
// a pulsing red ring, the one state the run pill cannot show (a green run with no artifact).
const DOT: Record<TicketStep, string> = {
    done: 'bg-primary border-link',
    current: 'bg-primary/20 border-link animate-pulse',
    pending: 'bg-transparent border-border',
    failed: 'bg-destructive/25 border-destructive',
    stalled: 'bg-destructive/10 border-destructive animate-pulse',
};

const LABEL: Record<TicketStep, string> = {
    done: 'text-foreground',
    current: 'text-link font-semibold',
    pending: 'text-muted-foreground',
    failed: 'text-destructive font-semibold',
    stalled: 'text-destructive font-semibold',
};

const DETAIL: Record<TicketStep, string> = {
    done: 'text-muted-foreground',
    current: 'text-link/80',
    pending: 'text-faint',
    failed: 'text-destructive/90',
    stalled: 'text-destructive/90',
};

/** The connector fill between cells: primary once the earlier cell is done, destructive to
 * mark a break at a failed or stalled cell, else the muted rail. */
const seg = (step: TicketStep | undefined): string =>
    step === 'done'
        ? 'bg-primary'
        : step === 'failed' || step === 'stalled'
          ? 'bg-destructive/60'
          : 'bg-border';

/**
 * One ticket's lifecycle as a strip: Ticket -> Resolve -> Review -> Merge, each cell
 * done / current / pending / failed / stalled, with a one-word state under it. The
 * maintenance sibling of PhaseStrip, and - when onSelect is given - the cockpit's spine: each
 * stop is a button that drives which substance + action the panes show, so a green-but-empty
 * resolve reads as a red 'stalled' Review you can click, not a dead end.
 */
export const TicketLine: React.FC<TicketLineProps> = ({ cells, selected, onSelect, className }) => (
    <div
        className={cn('flex items-start', className)}
        role={onSelect ? 'tablist' : 'group'}
        aria-label="Ticket lifecycle"
    >
        {cells.map((cell, index) => {
            const inner = (
                <>
                    <div className="flex w-full items-center">
                        <span
                            className={cn(
                                'h-0.5 flex-1 rounded-full',
                                index === 0 ? 'bg-transparent' : seg(cells[index - 1].step),
                            )}
                        />
                        <span
                            className={cn(
                                'mx-1 h-3.5 w-3.5 shrink-0 rounded-full border-2 transition-colors',
                                DOT[cell.step],
                                selected === cell.key &&
                                    'ring-2 ring-link/50 ring-offset-1 ring-offset-background',
                            )}
                            aria-hidden="true"
                        />
                        <span
                            className={cn(
                                'h-0.5 flex-1 rounded-full',
                                index === cells.length - 1 ? 'bg-transparent' : seg(cell.step),
                            )}
                        />
                    </div>
                    <span
                        className={cn(
                            'mt-2 text-center text-[11px] leading-tight',
                            LABEL[cell.step],
                        )}
                    >
                        {cell.label}
                    </span>
                    <span
                        className={cn(
                            'mt-0.5 text-center font-mono text-[9.5px] leading-tight',
                            DETAIL[cell.step],
                        )}
                    >
                        {cell.detail}
                    </span>
                </>
            );
            return onSelect ? (
                <button
                    key={cell.key}
                    type="button"
                    role="tab"
                    aria-selected={selected === cell.key}
                    onClick={() => onSelect(cell.key)}
                    title={cell.hint}
                    className={cn(
                        'flex flex-1 flex-col items-center rounded-md py-1 transition-colors hover:bg-primary/5',
                        selected === cell.key && 'bg-primary/5',
                    )}
                >
                    {inner}
                </button>
            ) : (
                <div key={cell.key} className="flex flex-1 flex-col items-center" title={cell.hint}>
                    {inner}
                </div>
            );
        })}
    </div>
);
