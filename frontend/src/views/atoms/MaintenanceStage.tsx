import { cn } from '@/utils';

import { STAGE_LABEL, STAGE_CLS } from '@/viewmodels/fleet/fleet.model';

export const MaintenanceStage: React.FC<{ stage: string }> = ({ stage }) =>
    stage ? (
        <span
            title={`maintenance stage: ${STAGE_LABEL[stage] ?? stage}`}
            className={cn(
                'hidden w-24 flex-none truncate rounded px-1.5 py-0.5 text-center font-mono text-[9px] sm:inline-block',
                STAGE_CLS[stage] ?? 'bg-muted text-muted-foreground',
            )}
        >
            {STAGE_LABEL[stage] ?? stage}
        </span>
    ) : (
        <span className="hidden w-24 flex-none sm:inline-block" aria-hidden="true" />
    );
