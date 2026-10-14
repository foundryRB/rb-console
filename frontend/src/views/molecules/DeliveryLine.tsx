import { Fragment } from 'react';
import type { PhaseView } from '@/models';
import { cn } from '@/utils';
import { GateSlot } from '@/views/atoms/GateSlot';
import { NODE, DOT, SUB } from '@/viewmodels/deliveries/phaseStyles.model';

export const DeliveryLine: React.FC<{
    phases: PhaseView[];
    selected: string | null;
    onSelect: (phase: string) => void;
}> = ({ phases, selected, onSelect }) => {
    return (
        <div className="flex items-stretch overflow-x-auto">
            {phases.map((p, i) => {
                const tone = p.tone ?? 'locked';
                const isSel = selected === p.name;
                return (
                    <Fragment key={p.name}>
                        <button
                            type="button"
                            onClick={() => onSelect(p.name)}
                            className={cn(
                                'min-w-[150px] flex-1 rounded-lg border p-3 text-left transition-colors',
                                NODE[tone],
                                isSel ? 'ring-1 ring-link/60' : 'hover:border-link/40',
                            )}
                        >
                            <span className="flex items-center gap-2">
                                <span className={cn('h-2 w-2 flex-none rounded-full', DOT[tone])} />
                                <span className="truncate text-sm font-semibold capitalize">
                                    {p.name}
                                </span>
                            </span>
                            <span
                                className={cn(
                                    'mt-1 block truncate font-mono text-[10.5px] font-semibold',
                                    SUB[tone],
                                )}
                            >
                                {p.sub_label}
                            </span>
                        </button>
                        {i < phases.length - 1 && p.gate && <GateSlot p={p} />}
                    </Fragment>
                );
            })}
        </div>
    );
};
