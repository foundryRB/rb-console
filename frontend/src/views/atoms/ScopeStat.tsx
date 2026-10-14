import { cn } from '@/utils';

export const ScopeStat: React.FC<{ k: React.ReactNode; l: string; ok?: boolean }> = ({
    k,
    l,
    ok,
}) => (
    <div className="rounded-lg border border-border bg-well/20 px-3.5 py-3">
        <div
            className={cn(
                'font-mono text-xl font-bold tabular-nums',
                ok && 'text-[hsl(var(--success))]',
            )}
        >
            {k}
        </div>
        <div className="mt-1 font-mono text-[9.5px] font-semibold uppercase tracking-widest text-muted-foreground">
            {l}
        </div>
    </div>
);
