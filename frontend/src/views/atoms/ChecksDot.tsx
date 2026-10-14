import { cn } from '@/utils';

export const ChecksDot: React.FC<{ checks: string }> = ({ checks }) => (
    <span
        className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground"
        title={`CI checks: ${checks}. A red check blocks the merge in every mode.`}
    >
        <span
            className={cn(
                'h-1.5 w-1.5 rounded-full',
                checks === 'green' && 'bg-[hsl(var(--success))]',
                checks === 'red' && 'bg-destructive',
                checks === 'pending' && 'bg-amber-400',
                checks === 'unknown' && 'bg-muted-foreground/40',
            )}
        />
        {checks}
    </span>
);
