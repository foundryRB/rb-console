import { cn } from '@/utils';

export const BacklogSkeleton: React.FC = () => (
    <div className="flex flex-col gap-2" role="status" aria-label="Loading tickets…">
        {['w-1/3', 'w-1/2', 'w-2/5', 'w-3/5', 'w-1/2', 'w-2/5'].map((w, i) => (
            <div
                key={i}
                className="flex items-center gap-2 rounded-lg border border-border bg-well/20 px-3.5 py-2.5"
            >
                <span className="h-3 w-11 flex-none animate-pulse rounded bg-muted/50" />
                <span className="h-3 w-8 flex-none animate-pulse rounded bg-muted/50" />
                <span className={cn('h-3 animate-pulse rounded bg-muted/40', w)} />
            </div>
        ))}
    </div>
);
