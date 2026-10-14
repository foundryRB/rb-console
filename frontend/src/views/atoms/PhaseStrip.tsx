import type { PhaseCell } from '@/viewmodels/deliveries';
import { cn } from '@/utils';

export interface PhaseStripProps {
    cells: PhaseCell[];
}

const DOT: Record<PhaseCell['step'], string> = {
    done: 'bg-primary border-link',
    current: 'bg-primary/20 border-link animate-pulse',
    pending: 'bg-transparent border-border',
};

const LABEL: Record<PhaseCell['step'], string> = {
    done: 'text-foreground',
    current: 'text-link font-semibold',
    pending: 'text-muted-foreground',
};

/**
 * The five-phase strip: Scope, Design, Intent+plan, Build+ship, Learn. Each cell is
 * marked done, current (pulsing), or pending. Connectors between cells fill in once
 * the earlier phase is done. Pure: the steps are derived in the ViewModel.
 */
export const PhaseStrip: React.FC<PhaseStripProps> = ({ cells }) => (
    <div className="flex items-start">
        {cells.map((cell, index) => (
            <div key={cell.key} className="flex flex-1 flex-col items-center">
                <div className="flex w-full items-center">
                    <span
                        className={cn(
                            'h-0.5 flex-1 rounded-full',
                            index === 0
                                ? 'bg-transparent'
                                : cells[index - 1].step === 'done'
                                  ? 'bg-primary'
                                  : 'bg-border',
                        )}
                    />
                    <span
                        className={cn(
                            'mx-1 h-3.5 w-3.5 shrink-0 rounded-full border-2 transition-colors',
                            DOT[cell.step],
                        )}
                        aria-hidden="true"
                    />
                    <span
                        className={cn(
                            'h-0.5 flex-1 rounded-full',
                            index === cells.length - 1
                                ? 'bg-transparent'
                                : cell.step === 'done'
                                  ? 'bg-primary'
                                  : 'bg-border',
                        )}
                    />
                </div>
                <span
                    className={cn('mt-2 text-center text-[11px] leading-tight', LABEL[cell.step])}
                >
                    {cell.label}
                </span>
            </div>
        ))}
    </div>
);
