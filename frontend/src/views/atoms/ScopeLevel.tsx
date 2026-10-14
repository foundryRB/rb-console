import { cn } from '@/utils';

import { sevClass } from '@/viewmodels/scope/scope.model';

export const ScopeLevel: React.FC<{ label: string; value: string; sev?: boolean }> = ({
    label,
    value,
    sev,
}) => (
    <span className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px]">
        <span className="text-faint">{label} </span>
        <span className={cn('font-semibold', sev ? sevClass(value) : 'text-foreground/80')}>
            {value}
        </span>
    </span>
);
